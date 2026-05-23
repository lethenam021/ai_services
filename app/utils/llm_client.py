"""
LLM Client — Wrapper cho OpenAI và Gemini API
Xử lý: logging token usage, error handling, retry logic, caching
Hỗ trợ cả OpenAI và Gemini, chọn model qua config
"""
import asyncio
import logging
import time
import hashlib
import json
from typing import AsyncGenerator, Optional, Any, TYPE_CHECKING
from enum import Enum

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError, AuthenticationError
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

if TYPE_CHECKING:
    from google.generativeai import GenerativeModel
    from google.generativeai.types.generation_types import GenerationConfigDict

from app.core.config import settings
from app.utils.usage_logger import log_api_usage

logger = logging.getLogger(__name__)

# ============================================================
# LLM Provider Enum
# ============================================================


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"


# ============================================================
# Redis Client for Caching
# ============================================================
_redis_client: Optional[Any] = None


async def get_redis_client():
    """Lazy load Redis client"""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as redis_async
            _redis_client = redis_async.from_url(
                settings.REDIS_URL or "redis://localhost:6379",
                decode_responses=True
            )
            await _redis_client.ping()
            logger.info("Redis connected for LLM caching")
        except Exception as e:
            logger.warning(f"Redis not available, caching disabled: {e}")
            _redis_client = None
    return _redis_client


async def get_cache_key(system: str, user: str, max_tokens: int) -> str:
    """Tạo cache key từ prompt"""
    content = f"{system}|{user}|{max_tokens}"
    return f"llm_cache:{hashlib.md5(content.encode()).hexdigest()}"


async def get_cached_response(system: str, user: str, max_tokens: int) -> Optional[str]:
    """Lấy response từ cache nếu có"""
    try:
        client = await get_redis_client()
        if client:
            cache_key = await get_cache_key(system, user, max_tokens)
            cached = await client.get(cache_key)
            if cached:
                logger.info(f"Cache hit for key: {cache_key[:20]}...")
                return cached
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


async def set_cached_response(system: str, user: str, max_tokens: int, response: str, ttl: int = 21600):
    """Lưu response vào cache (TTL = 1 giờ)"""
    try:
        client = await get_redis_client()
        if client:
            cache_key = await get_cache_key(system, user, max_tokens)
            await client.setex(cache_key, ttl, response)
            logger.info(f"Cached response for key: {cache_key[:20]}...")
    except Exception as e:
        logger.warning(f"Cache write error: {e}")

# ============================================================
# Initialize Clients
# ============================================================
# OpenAI Client
_openai_client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
)

# Gemini Client
_gemini_model: Optional["GenerativeModel"] = None
USE_GEMINI = False

# Chỉ import và khởi tạo Gemini nếu có API key
if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "":
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        gemini_model_name = getattr(
            settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        _gemini_model = genai.GenerativeModel(gemini_model_name)
        USE_GEMINI = True
        logger.info(f"Gemini initialized with model: {gemini_model_name}")
    except ImportError:
        logger.warning(
            "google-generativeai package not installed. Install with: pip install google-generativeai")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini: {e}")

# Lấy provider từ config (mặc định là openai)
CURRENT_PROVIDER = getattr(settings, 'LLM_PROVIDER', 'openai')
if CURRENT_PROVIDER == "gemini" and not USE_GEMINI:
    logger.warning(
        "Gemini requested but not available, falling back to OpenAI")
    CURRENT_PROVIDER = "openai"

# ============================================================
# System Prompts
# ============================================================
SYSTEM_PROMPT_SUGGESTION = """Bạn là chuyên gia về prompt engineering và giảng dạy AI.
Nhiệm vụ: Phân tích prompt của người học và đưa ra nhận xét chi tiết bằng tiếng Việt.
Hãy:
1. Chỉ ra điểm mạnh của prompt
2. Giải thích cụ thể điểm yếu cần cải thiện
3. Đưa ra phiên bản prompt cải thiện hoàn chỉnh
4. Giải thích tại sao phiên bản mới tốt hơn
Trả lời ngắn gọn, dễ hiểu, phù hợp với người mới học AI."""

SYSTEM_PROMPT_QUIZ = """Bạn là chuyên gia giáo dục, nhiệm vụ tạo câu hỏi trắc nghiệm từ nội dung bài học.
Hãy tạo câu hỏi đa dạng, phù hợp với độ khó được yêu cầu.
Trả về định dạng JSON hợp lệ."""

SYSTEM_PROMPT_EXPERT = """Bạn là trợ giảng AI, nhiệm vụ trả lời câu hỏi của học viên một cách dễ hiểu, chính xác.
Sử dụng ví dụ cụ thể và ngôn ngữ đơn giản."""

# ============================================================
# Core LLM Functions
# ============================================================


async def _call_openai(
    messages: list[ChatCompletionMessageParam],
    max_tokens: int,
    temperature: float = 0.7,
    stream: bool = False,
) -> Any:
    """Gọi OpenAI API với retry logic"""
    max_retries = 3
    retry_delay = 1
    last_error = None

    logger.debug(
        f"OpenAI request - Model: {settings.OPENAI_MODEL}, Max tokens: {max_tokens}, Stream: {stream}")
    logger.debug(f"Base URL: {settings.OPENAI_BASE_URL}")
    logger.debug(f"Messages count: {len(messages)}")

    for attempt in range(max_retries):
        try:
            if stream:
                logger.info(
                    f"[Attempt {attempt + 1}/{max_retries}] Gọi OpenAI API (streaming)...")
                return await _openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                    stream=True,
                )
            else:
                logger.info(
                    f"[Attempt {attempt + 1}/{max_retries}] Gọi OpenAI API (non-streaming)...")
                response = await _openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                )
                logger.info(
                    f"✅ OpenAI response thành công (usage: {response.usage})")
                return response
        except AuthenticationError as e:
            last_error = e
            logger.error(
                f"[Attempt {attempt + 1}/{max_retries}] 🔐 Authentication Error: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Sẽ retry sau {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise
        except RateLimitError as e:
            last_error = e
            logger.error(
                f"[Attempt {attempt + 1}/{max_retries}] ⏱️ Rate Limit Error: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * 2
                logger.warning(f"Sẽ retry sau {wait_time}s...")
                await asyncio.sleep(wait_time)
                retry_delay *= 2
            else:
                raise
        except APITimeoutError as e:
            last_error = e
            logger.error(
                f"[Attempt {attempt + 1}/{max_retries}] ⏳ Timeout Error: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Sẽ retry sau {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise
        except APIError as e:
            last_error = e
            logger.error(
                f"[Attempt {attempt + 1}/{max_retries}] ❌ API Error: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Sẽ retry sau {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

    if last_error:
        raise last_error


async def _call_gemini(
    messages: list[ChatCompletionMessageParam],
    max_tokens: int,
    temperature: float = 0.7,
    stream: bool = False,
) -> Any:
    """Gọi Gemini API với retry logic"""
    if _gemini_model is None:
        raise RuntimeError("Gemini model is not initialized")

    # Chuyển đổi messages format từ OpenAI sang Gemini
    user_message = ""
    system_message = ""

    for msg in messages:
        if msg["role"] == "system":
            system_message = msg["content"]
        elif msg["role"] == "user":
            user_message = msg["content"]

    # Ghép system prompt vào user message nếu có
    if system_message:
        full_prompt = f"{system_message}\n\n{user_message}"
    else:
        full_prompt = user_message

    generation_config: "GenerationConfigDict" = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }

    max_retries = 3
    retry_delay = 1
    last_error = None

    logger.debug(
        f"Gemini request - Max tokens: {max_tokens}, Stream: {stream}")
    try:
        prompt_len = len(full_prompt) if isinstance(
            full_prompt, str) else "N/A"
        logger.debug(f"Prompt length: {prompt_len} chars")
    except (TypeError, AttributeError):
        logger.debug(f"Prompt type: {type(full_prompt)}")

    for attempt in range(max_retries):
        try:
            if stream:
                logger.info(
                    f"[Attempt {attempt + 1}/{max_retries}] Gọi Gemini API (streaming)...")
                response = await _gemini_model.generate_content_async(
                    full_prompt,
                    generation_config=generation_config,
                    stream=True,
                )
                logger.info(f"✅ Gemini response thành công (streaming)")
                return response
            else:
                logger.info(
                    f"[Attempt {attempt + 1}/{max_retries}] Gọi Gemini API (non-streaming)...")
                response = await _gemini_model.generate_content_async(
                    full_prompt,
                    generation_config=generation_config,
                )
                logger.info(f"✅ Gemini response thành công")
                return response
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            logger.error(
                f"[Attempt {attempt + 1}/{max_retries}] ❌ Gemini {error_type}: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Sẽ retry sau {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

    if last_error:
        raise last_error


async def _extract_gemini_text(response) -> str:
    """Trích xuất text từ Gemini response"""
    if hasattr(response, 'text'):
        return response.text
    elif hasattr(response, 'candidates') and response.candidates:
        return response.candidates[0].content.parts[0].text
    return ""

# ============================================================
# Stream Suggestion
# ============================================================


async def stream_suggestion(
    anonymized_prompt: str,
    weak_criteria: list[str],
    domain: str,
    correlation_id: str,
    user_id: int,
) -> AsyncGenerator[str, None]:
    """Stream gợi ý cải thiện prompt từ LLM"""
    # Stream không cache được vì là streaming
    user_message = f"""Domain: {domain}
Tiêu chí yếu: {', '.join(weak_criteria)}

Prompt của người học:
{anonymized_prompt}

Hãy phân tích và đưa ra nhận xét + phiên bản cải thiện."""

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT_SUGGESTION},
        {"role": "user", "content": user_message},
    ]

    start_time = time.monotonic()
    prompt_tokens = 0
    completion_tokens = 0
    status = "success"

    try:
        if CURRENT_PROVIDER == "gemini" and USE_GEMINI:
            response = await _call_gemini(
                messages=messages,
                max_tokens=settings.MAX_TOKENS_PER_REQUEST,
                temperature=0.7,
                stream=True,
            )
            async for chunk in response:
                if hasattr(chunk, 'text') and chunk.text:
                    token = chunk.text
                    completion_tokens += len(token)
                    yield token
        else:
            stream = await _call_openai(
                messages=messages,
                max_tokens=settings.MAX_TOKENS_PER_REQUEST,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    completion_tokens += 1
                    yield token
                if hasattr(chunk, 'usage') and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens

    except APITimeoutError:
        status = "timeout"
        logger.error("[%s] LLM timeout", correlation_id)
        yield "\n\n[Hệ thống đang bận, vui lòng thử lại sau]"
    except RateLimitError:
        status = "rate_limit"
        logger.error("[%s] LLM rate limit hit", correlation_id)
        yield "\n\n[Đã đạt giới hạn API, vui lòng thử lại sau ít phút]"
    except Exception as e:
        status = "error"
        logger.error("[%s] LLM API error: %s", correlation_id, str(e))
        yield f"\n\n[Lỗi kết nối AI: {str(e)}]"
    finally:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        await log_api_usage(
            correlation_id=correlation_id,
            user_id=user_id,
            service_name="suggestion",
            model=settings.OPENAI_MODEL if CURRENT_PROVIDER == "openai" else getattr(
                settings, 'GEMINI_MODEL', 'gemini-1.5-flash'),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status=status,
        )

# ============================================================
# Non-streaming Complete (CÓ CACHE)
# ============================================================


async def complete(
    system: str,
    user: str,
    correlation_id: str,
    user_id: int,
    service_name: str,
    max_tokens: int = 800,
    use_cache: bool = True,
) -> str:
    """Non-streaming completion cho các service không cần stream (có cache)"""
    start_time = time.monotonic()
    status = "success"
    result = ""

    # 1. Kiểm tra cache (nếu bật)
    if use_cache:
        cached = await get_cached_response(system, user, max_tokens)
        if cached:
            logger.info(f"[{correlation_id}] Cache hit for {service_name}")
            return cached

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        if CURRENT_PROVIDER == "gemini" and USE_GEMINI:
            response = await _call_gemini(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
                stream=False,
            )
            result = await _extract_gemini_text(response)
        else:
            response = await _call_openai(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
                stream=False,
            )
            result = response.choices[0].message.content or ""

        # 2. Lưu vào cache (nếu bật và không phải lỗi)
        if use_cache and result:
            await set_cached_response(system, user, max_tokens, result)

        return result

    except Exception as e:
        status = "error"
        logger.error("[%s] LLM error in %s: %s",
                     correlation_id, service_name, str(e))
        raise
    finally:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        await log_api_usage(
            correlation_id=correlation_id,
            user_id=user_id,
            service_name=service_name,
            model=settings.OPENAI_MODEL if CURRENT_PROVIDER == "openai" else getattr(
                settings, 'GEMINI_MODEL', 'gemini-1.5-flash'),
            prompt_tokens=len(user.split()),
            completion_tokens=len(result.split()),
            latency_ms=latency_ms,
            status=status,
        )

# ============================================================
# Quiz Generation (có cache)
# ============================================================


async def generate_quiz(
    lesson_content: str,
    num_questions: int,
    difficulty: str,
    question_types: list[str],
    correlation_id: str,
    user_id: int,
) -> str:
    """Tạo quiz từ nội dung bài học (có cache)"""
    user_prompt = f"""Nội dung bài học:
{lesson_content}

Yêu cầu:
- Số lượng câu hỏi: {num_questions}
- Độ khó: {difficulty}
- Loại câu hỏi: {', '.join(question_types)}

Hãy tạo câu hỏi trắc nghiệm dựa trên nội dung trên."""

    return await complete(
        system=SYSTEM_PROMPT_QUIZ,
        user=user_prompt,
        correlation_id=correlation_id,
        user_id=user_id,
        service_name="quiz_generation",
        max_tokens=2000,
        use_cache=True,  # Bật cache cho quiz
    )

# ============================================================
# Expert Assistance (có cache)
# ============================================================


async def expert_assist(
    question: str,
    expertise_area: str,
    context: str,
    correlation_id: str,
    user_id: int,
) -> str:
    """Trợ giúp từ chuyên gia AI (có cache)"""
    user_prompt = f"""Lĩnh vực: {expertise_area}
Ngữ cảnh: {context}
Câu hỏi: {question}

Hãy trả lời câu hỏi một cách chi tiết và dễ hiểu."""

    return await complete(
        system=SYSTEM_PROMPT_EXPERT,
        user=user_prompt,
        correlation_id=correlation_id,
        user_id=user_id,
        service_name="expert_assist",
        max_tokens=1500,
        use_cache=True,  # Bật cache cho expert
    )

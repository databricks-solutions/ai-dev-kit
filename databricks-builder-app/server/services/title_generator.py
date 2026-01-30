"""AI-powered conversation title generation.

Uses Claude to generate concise, descriptive titles for conversations
based on the first user message.
"""

import asyncio
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# Cache the Anthropic client
_client = None


def _get_client() -> anthropic.AsyncAnthropic:
  """Get or create the Anthropic client."""
  global _client
  if _client is None:
    # Use the same auth as the main agent (from .claude/settings.json)
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    base_url = os.environ.get('ANTHROPIC_BASE_URL')

    if base_url:
      _client = anthropic.AsyncAnthropic(
        api_key=api_key or 'unused',  # Databricks auth doesn't need real key
        base_url=base_url,
      )
    else:
      _client = anthropic.AsyncAnthropic(api_key=api_key)

  return _client


async def generate_title(message: str, max_length: int = 40) -> str:
  """Generate a concise title for a conversation based on the first message.

  Args:
      message: The user's first message in the conversation
      max_length: Maximum length of the generated title

  Returns:
      A short, descriptive title (or truncated message as fallback)
  """
  # Fallback: truncate message
  fallback = message[:max_length].strip()
  if len(message) > max_length:
    fallback = fallback.rsplit(' ', 1)[0] + '...'

  try:
    client = _get_client()

    response = await asyncio.wait_for(
      client.messages.create(
        model='claude-3-5-haiku-latest',
        max_tokens=50,
        messages=[
          {
            'role': 'user',
            'content': f'''Generate a very short title (3-6 words max) for this chat message.
The title should capture the main intent/topic. No quotes, no punctuation at the end.

Message: {message[:500]}

Title:''',
          }
        ],
      ),
      timeout=5.0,  # 5 second timeout
    )

    # Extract title from response
    title = response.content[0].text.strip()

    # Clean up: remove quotes, limit length
    title = title.strip('"\'')
    if len(title) > max_length:
      title = title[:max_length].rsplit(' ', 1)[0] + '...'

    return title if title else fallback

  except asyncio.TimeoutError:
    logger.warning('Title generation timed out, using fallback')
    return fallback
  except Exception as e:
    logger.warning(f'Title generation failed: {e}, using fallback')
    return fallback


async def generate_title_async(
  message: str,
  conversation_id: str,
  user_email: str,
  project_id: str,
) -> None:
  """Generate a title and update the conversation in the background.

  This runs in a fire-and-forget pattern so it doesn't block the main response.

  Args:
      message: The user's first message
      conversation_id: ID of the conversation to update
      user_email: User's email for storage access
      project_id: Project ID for storage access
  """
  try:
    title = await generate_title(message)

    # Update the conversation title
    from .storage import ConversationStorage

    storage = ConversationStorage(user_email, project_id)
    await storage.update_title(conversation_id, title)
    logger.info(f'Updated conversation {conversation_id} title to: {title}')

  except Exception as e:
    logger.warning(f'Failed to update conversation title: {e}')

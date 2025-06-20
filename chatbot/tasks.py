from celery import shared_task
from django.utils.timezone import now
from django.core.cache import cache

from .models import Conversation, Message

@shared_task
def process_message_group(conversation_id):
    group_key = f"group:{conversation_id}"
    message_ids = cache.get(group_key, [])

    if not message_ids:
        return

    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return

    if not conversation.is_open():
        return

    inbound_messages = Message.objects.filter(
        id__in=message_ids,
        conversation=conversation,
        type='INBOUND'
    ).order_by('timestamp')

    if not inbound_messages.exists():
        return

    content = "Mensagens recebidas:\n" + "\n".join(str(m.id) for m in inbound_messages)

    Message.objects.create(
        conversation=conversation,
        type='OUTBOUND',
        content=content,
        timestamp=now()
    )

    # Remove Redis group after processing
    cache.delete(group_key)
    cache.delete(f"group-lock:{conversation_id}")

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now, is_naive
from django.core.cache import cache
import datetime

from .models import Conversation, Message
from .tasks import process_message_group
import uuid

from rest_framework.generics import RetrieveAPIView
from .models import Conversation
from .serializers import ConversationSerializer


class ConversationDetailView(RetrieveAPIView):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    lookup_field = 'id'

class WebhookView(APIView):

    def post(self, request):
        payload = request.data

        event_type = payload.get("type")
        timestamp = parse_datetime(payload.get("timestamp"))
        data = payload.get("data", {})

        if not event_type or not timestamp or not isinstance(data, dict):
            return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

        # NEW_CONVERSATION
        if event_type == "NEW_CONVERSATION":
            return self._handle_new_conversation(data, timestamp)

        # NEW_MESSAGE
        elif event_type == "NEW_MESSAGE":
            return self._handle_new_message(data, timestamp)

        # CLOSE_CONVERSATION
        elif event_type == "CLOSE_CONVERSATION":
            return self._handle_close_conversation(data)

        return Response({"error": "Unknown type"}, status=status.HTTP_400_BAD_REQUEST)

    def _handle_new_conversation(self, data, timestamp):
        conversation_id = data.get("id")
        payload_timestamp = now()
        if is_naive(payload_timestamp):
            payload_timestamp = payload_timestamp.replace(tzinfo=datetime.timezone.utc)
        if not conversation_id:
            return Response({"error": "Missing conversation ID"}, status=status.HTTP_400_BAD_REQUEST)

        if Conversation.objects.filter(id=conversation_id).exists():
            return Response({"error": "Conversation already exists"}, status=status.HTTP_400_BAD_REQUEST)

        Conversation.objects.create(id=conversation_id)

        for key in cache.iter_keys(f"buffer:{conversation_id}:*"):
            message = cache.get(key)
            if message:
                msg_timestamp = parse_datetime(message["timestamp"])
                if is_naive(msg_timestamp):
                    msg_timestamp = msg_timestamp.replace(tzinfo=datetime.timezone.utc)
                time_diff = (payload_timestamp - msg_timestamp).total_seconds()
                if time_diff <= 6:
                    conversation = Conversation.objects.get(id=conversation_id)
                    Message.objects.create(
                        id=message["id"],
                        conversation=conversation,
                        type='INBOUND',
                        content=message["content"],
                        timestamp=msg_timestamp
                    )
                    # Atualiza agrupamento
                    group_key = f"group:{conversation_id}"
                    message_ids = cache.get(group_key, [])
                    message_ids.append(str(message["id"]))
                    cache.set(group_key, message_ids, timeout=10)

                    process_message_group.apply_async((conversation_id,), countdown=5)

            cache.delete(key)

        return Response({"message": "Conversation created"}, status=status.HTTP_201_CREATED)

    def _handle_new_message(self, data, timestamp):
        msg_id = data.get("id")
        content = data.get("content")
        conv_id = data.get("conversation_id")

        if not (msg_id and content and conv_id and timestamp):
            return Response({"error": "Invalid message data"}, status=status.HTTP_400_BAD_REQUEST)

        conversation = Conversation.objects.filter(id=conv_id).first()
        if not conversation:
            buffer_key = f"buffer:{conv_id}:{msg_id}"
            cache.set(buffer_key, {"id": msg_id, "content": content, "timestamp": now().isoformat()}, timeout=10)
            return Response({"message": "Conversation not found yet, message buffered"}, status=status.HTTP_202_ACCEPTED)

        if not conversation.is_open():
            return Response({"error": "Conversation is closed"}, status=status.HTTP_400_BAD_REQUEST)

        Message.objects.create(
            id=msg_id,
            conversation=conversation,
            type='INBOUND',
            content=content,
            timestamp=timestamp
        )

        # cache group
        group_key = f"group:{conv_id}"
        lock_key = f"group-lock:{conv_id}"

        message_ids = cache.get(group_key, [])
        message_ids.append(str(msg_id))
        cache.set(group_key, message_ids, timeout=10)

        # Se ainda não existe uma task agendada, agende e marque com o lock
        if cache.add(lock_key, True, timeout=6):
            cache.set(lock_key, True, timeout=6)  # lock com TTL curto
            process_message_group.apply_async((conv_id,), countdown=5)

        return Response({"message": "Message received"}, status=status.HTTP_202_ACCEPTED)

    def _handle_close_conversation(self, data):
        conv_id = data.get("id")
        if not conv_id:
            return Response({"error": "Missing conversation ID"}, status=status.HTTP_400_BAD_REQUEST)

        conversation = Conversation.objects.filter(id=conv_id).first()
        if not conversation:
            return Response({"error": "Conversation not found"}, status=status.HTTP_400_BAD_REQUEST)

        if not conversation.is_open():
            return Response({"error": "Conversation already closed"}, status=status.HTTP_400_BAD_REQUEST)

        conversation.close()
        return Response({"message": "Conversation closed"}, status=status.HTTP_200_OK)

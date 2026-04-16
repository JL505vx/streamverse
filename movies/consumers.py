import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied

from .models import WatchParty, WatchPartyMessage
from .watch_party import (
    get_watch_party_messages,
    mark_watch_party_member_disconnected,
    serialize_watch_party,
    serialize_watch_party_message,
    touch_watch_party_member,
    user_can_control_watch_party,
    user_is_in_watch_party,
)


logger = logging.getLogger(__name__)


class WatchPartyConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        self.slug = (self.scope.get('url_route', {}).get('kwargs', {}).get('slug') or '').strip()
        self.code = ((self.scope.get('url_route', {}).get('kwargs', {}).get('code') or '').strip()).upper()

        if not self.user or not self.user.is_authenticated or not self.slug or not self.code:
            await self.close(code=4401)
            return

        try:
            self.party = await self._get_party()
        except WatchParty.DoesNotExist:
            await self.close(code=4404)
            return
        except PermissionDenied:
            await self.close(code=4403)
            return

        self.group_name = f'watch_party_{self.party.code}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._touch_connected_member(True)
        await self.send_snapshot('snapshot')
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'party.event',
                'event_name': 'party.presence',
                'code': self.party.code,
                'movie_slug': self.party.movie.slug,
            },
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', '')
        if group_name:
            await self._touch_connected_member(False)
            await self.channel_layer.group_discard(group_name, self.channel_name)
            await self.channel_layer.group_send(
                group_name,
                {
                    'type': 'party.event',
                    'event_name': 'party.presence',
                    'code': self.code,
                    'movie_slug': self.slug,
                },
            )

    async def receive_json(self, content, **kwargs):
        event_type = (content.get('type') or '').strip()
        if not event_type:
            return

        try:
            self.party = await self._get_party()
        except WatchParty.DoesNotExist:
            await self.send_json({'type': 'party.closed'})
            await self.close(code=4404)
            return
        except PermissionDenied:
            await self.close(code=4403)
            return

        await self._touch_connected_member(True)

        if event_type == 'heartbeat':
            await self.send_snapshot('heartbeat')
            return

        if event_type == 'playback_sync':
            await self._handle_playback_sync(content)
            return

        if event_type == 'control_mode':
            await self._handle_control_mode(content)
            return

        if event_type == 'chat_message':
            await self._handle_chat_message(content)
            return

    async def party_event(self, event):
        event_name = event.get('event_name')
        if event_name == 'party.closed':
            await self.send_json({'type': 'party.closed'})
            await self.close(code=4404)
            return

        if event_name == 'party.message':
            message = await self._get_message_payload(event.get('message_id'))
            if message:
                await self.send_json({'type': 'party.message', 'message': message})
            return

        await self.send_snapshot(event_name or 'party.state')

    async def send_snapshot(self, event_name):
        snapshot = await self._serialize_party_snapshot()
        await self.send_json(
            {
                'type': event_name,
                'party': snapshot['party'],
                'messages': snapshot['messages'],
            }
        )

    async def _handle_playback_sync(self, content):
        playback_state = (content.get('playback_state') or '').strip()
        current_time_seconds = content.get('current_time_seconds', 0)

        try:
            current_time_seconds = max(0, float(current_time_seconds or 0))
        except (TypeError, ValueError):
            await self.send_json({'type': 'party.error', 'error': 'invalid_time'})
            return

        if playback_state not in {
            WatchParty.PlaybackState.PAUSED,
            WatchParty.PlaybackState.PLAYING,
        }:
            await self.send_json({'type': 'party.error', 'error': 'invalid_state'})
            return

        allowed = await database_sync_to_async(user_can_control_watch_party)(self.party, self.user)
        if not allowed:
            await self.send_json({'type': 'party.error', 'error': 'host_only'})
            return

        await self._save_party_state(playback_state, current_time_seconds)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'party.event',
                'event_name': 'party.state',
                'code': self.party.code,
                'movie_slug': self.party.movie.slug,
            },
        )

    async def _handle_control_mode(self, content):
        control_mode = (content.get('control_mode') or '').strip()
        if control_mode not in {
            WatchParty.ControlMode.HOST,
            WatchParty.ControlMode.SHARED,
        }:
            await self.send_json({'type': 'party.error', 'error': 'invalid_control_mode'})
            return

        is_host = await database_sync_to_async(lambda party, user: party.host_id == user.id)(self.party, self.user)
        if not is_host:
            await self.send_json({'type': 'party.error', 'error': 'host_only'})
            return

        await self._save_control_mode(control_mode)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'party.event',
                'event_name': 'party.state',
                'code': self.party.code,
                'movie_slug': self.party.movie.slug,
            },
        )

    async def _handle_chat_message(self, content):
        text = (content.get('text') or '').strip()
        if not text:
            await self.send_json({'type': 'party.error', 'error': 'empty_message'})
            return
        if len(text) > 400:
            await self.send_json({'type': 'party.error', 'error': 'message_too_long'})
            return

        is_member = await database_sync_to_async(user_is_in_watch_party)(self.party, self.user)
        if not is_member:
            await self.close(code=4403)
            return

        message_id = await self._create_message(text)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'party.event',
                'event_name': 'party.message',
                'message_id': message_id,
                'code': self.party.code,
                'movie_slug': self.party.movie.slug,
            },
        )

    @database_sync_to_async
    def _get_party(self):
        party = (
            WatchParty.objects.select_related('movie', 'host', 'last_action_by')
            .get(code=self.code, movie__slug=self.slug, is_active=True)
        )
        if not user_is_in_watch_party(party, self.user):
            raise PermissionDenied('not_joined')
        return party

    @database_sync_to_async
    def _touch_connected_member(self, is_connected):
        touch_watch_party_member(self.party, self.user, is_connected=is_connected)
        if not is_connected:
            mark_watch_party_member_disconnected(self.party, self.user)

    @database_sync_to_async
    def _serialize_party_snapshot(self):
        refreshed_party = WatchParty.objects.select_related('movie', 'host', 'last_action_by').get(pk=self.party.pk)
        self.party = refreshed_party
        return {
            'party': serialize_watch_party(refreshed_party, user=self.user),
            'messages': [
                serialize_watch_party_message(message, current_user=self.user)
                for message in get_watch_party_messages(refreshed_party)
            ],
        }

    @database_sync_to_async
    def _save_party_state(self, playback_state, current_time_seconds):
        WatchParty.objects.filter(pk=self.party.pk).update(
            playback_state=playback_state,
            current_time_seconds=current_time_seconds,
            last_action_by_id=self.user.id,
        )

    @database_sync_to_async
    def _save_control_mode(self, control_mode):
        WatchParty.objects.filter(pk=self.party.pk).update(
            control_mode=control_mode,
            last_action_by_id=self.user.id,
        )

    @database_sync_to_async
    def _create_message(self, text):
        message = WatchPartyMessage.objects.create(
            party_id=self.party.pk,
            user=self.user,
            text=text,
        )
        return message.pk

    @database_sync_to_async
    def _get_message_payload(self, message_id):
        if not message_id:
            return None
        try:
            message = WatchPartyMessage.objects.select_related('user').get(pk=message_id, party_id=self.party.pk)
        except WatchPartyMessage.DoesNotExist:
            logger.warning('Mensaje de watch party no encontrado message_id=%s party=%s', message_id, self.party.pk)
            return None
        return serialize_watch_party_message(message, current_user=self.user)

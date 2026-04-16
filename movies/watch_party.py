from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import WatchParty, WatchPartyMember, WatchPartyMessage


WATCH_PARTY_MEMBER_STALE_SECONDS = getattr(settings, 'WATCH_PARTY_MEMBER_STALE_SECONDS', 120)
WATCH_PARTY_MESSAGE_HISTORY_LIMIT = getattr(settings, 'WATCH_PARTY_MESSAGE_HISTORY_LIMIT', 24)


def touch_watch_party_member(party, user, *, is_connected=None):
    member, created = WatchPartyMember.objects.get_or_create(party=party, user=user)
    updates = {'last_seen': timezone.now()}
    if is_connected is not None:
        updates['is_connected'] = is_connected

    WatchPartyMember.objects.filter(pk=member.pk).update(**updates)
    for field, value in updates.items():
        setattr(member, field, value)
    return member, created


def mark_watch_party_member_disconnected(party, user):
    WatchPartyMember.objects.filter(party=party, user=user).update(
        is_connected=False,
        last_seen=timezone.now(),
    )


def user_is_in_watch_party(party, user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.id == party.host_id:
        return True
    return party.members.filter(user=user).exists()


def user_can_control_watch_party(party, user):
    if not user_is_in_watch_party(party, user):
        return False
    if user.id == party.host_id:
        return True
    return party.control_mode == WatchParty.ControlMode.SHARED


def get_watch_party_members(party):
    freshness_limit = timezone.now() - timedelta(seconds=WATCH_PARTY_MEMBER_STALE_SECONDS)
    members = list(
        party.members.select_related('user')
        .filter(Q(is_connected=True) | Q(last_seen__gte=freshness_limit))
        .order_by('joined_at')
    )

    if not any(member.user_id == party.host_id for member in members):
        members.insert(
            0,
            WatchPartyMember(
                party=party,
                user=party.host,
                joined_at=party.created_at,
                last_seen=party.last_action_at,
                is_connected=False,
            ),
        )

    return members


def serialize_watch_party_message(message, current_user=None):
    return {
        'id': message.id,
        'username': message.user.username,
        'text': message.text,
        'created_at': timezone.localtime(message.created_at).isoformat(),
        'is_self': bool(current_user and current_user.id == message.user_id),
    }


def get_watch_party_messages(party, limit=WATCH_PARTY_MESSAGE_HISTORY_LIMIT):
    return list(
        party.messages.select_related('user')
        .order_by('-created_at')[:limit]
    )[::-1]


def serialize_watch_party(party, user=None, request=None):
    active_members = get_watch_party_members(party)
    invite_url = ''
    if request is not None:
        invite_url = request.build_absolute_uri(f"{reverse('movie_detail', args=[party.movie.slug])}?party={party.code}")

    return {
        'code': party.code,
        'movie_slug': party.movie.slug,
        'movie_title': party.movie.title,
        'playback_state': party.playback_state,
        'current_time_seconds': round(float(party.current_time_seconds or 0), 2),
        'last_action_at': timezone.localtime(party.last_action_at).isoformat(),
        'last_action_by': party.last_action_by.username if party.last_action_by else party.host.username,
        'host_username': party.host.username,
        'control_mode': party.control_mode,
        'participant_count': len(active_members),
        'participants': [
            {
                'username': member.user.username,
                'is_host': member.user_id == party.host_id,
                'is_online': bool(getattr(member, 'is_connected', False)),
                'last_seen': timezone.localtime(member.last_seen).isoformat() if member.last_seen else '',
            }
            for member in active_members
        ],
        'is_host': bool(user and user.id == party.host_id),
        'can_control': bool(user and user_can_control_watch_party(party, user)),
        'is_active': party.is_active,
        'invite_url': invite_url,
    }

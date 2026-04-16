import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Genre, Movie, WatchParty, WatchPartyMessage


class WatchPartyFlowTests(TestCase):
    def setUp(self):
        self.genre = Genre.objects.create(name='Animacion')
        self.movie = Movie.objects.create(
            title='Valiente',
            genre=self.genre,
            release_year=2012,
            is_published=True,
            video_url='https://cdn.example.com/valiente.mp4',
        )
        self.host = User.objects.create_user(username='anita', password='secret12345')
        self.guest = User.objects.create_user(username='pablo', password='secret12345')
        self.host_client = Client()
        self.guest_client = Client()
        self.host_client.force_login(self.host)
        self.guest_client.force_login(self.guest)

    def test_host_creates_party_guest_joins_and_reads_synced_state(self):
        create_response = self.host_client.post(
            reverse('watch_party_create', args=[self.movie.slug]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertTrue(create_payload['ok'])
        code = create_payload['party']['code']

        join_response = self.guest_client.post(
            reverse('watch_party_join', args=[self.movie.slug]),
            data=json.dumps({'code': code}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(join_response.status_code, 200)
        join_payload = join_response.json()
        self.assertTrue(join_payload['ok'])
        self.assertFalse(join_payload['party']['can_control'])

        sync_response = self.host_client.post(
            reverse('watch_party_sync', args=[self.movie.slug, code]),
            data=json.dumps({'playback_state': 'playing', 'current_time_seconds': 83.5}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(sync_response.status_code, 200)
        sync_payload = sync_response.json()
        self.assertEqual(sync_payload['party']['playback_state'], 'playing')

        state_response = self.guest_client.get(
            reverse('watch_party_state', args=[self.movie.slug, code]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(state_response.status_code, 200)
        state_payload = state_response.json()
        self.assertTrue(state_payload['ok'])
        self.assertEqual(state_payload['party']['code'], code)
        self.assertEqual(state_payload['party']['host_username'], self.host.username)
        self.assertFalse(state_payload['party']['can_control'])
        self.assertGreaterEqual(state_payload['party']['participant_count'], 2)

    def test_guest_cannot_sync_and_host_can_close_party(self):
        code = self.host_client.post(
            reverse('watch_party_create', args=[self.movie.slug]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()['party']['code']

        self.guest_client.post(
            reverse('watch_party_join', args=[self.movie.slug]),
            data=json.dumps({'code': code}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        forbidden_response = self.guest_client.post(
            reverse('watch_party_sync', args=[self.movie.slug, code]),
            data=json.dumps({'playback_state': 'paused', 'current_time_seconds': 12}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(forbidden_response.status_code, 403)
        self.assertEqual(forbidden_response.json()['error'], 'host_only')

        leave_response = self.host_client.post(
            reverse('watch_party_leave', args=[self.movie.slug, code]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(leave_response.status_code, 200)
        self.assertTrue(leave_response.json()['closed'])

        state_after_close = self.guest_client.get(
            reverse('watch_party_state', args=[self.movie.slug, code]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(state_after_close.status_code, 404)

    def test_guest_can_sync_when_party_control_is_shared(self):
        code = self.host_client.post(
            reverse('watch_party_create', args=[self.movie.slug]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()['party']['code']

        self.guest_client.post(
            reverse('watch_party_join', args=[self.movie.slug]),
            data=json.dumps({'code': code}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        WatchParty.objects.filter(code=code).update(control_mode=WatchParty.ControlMode.SHARED)

        sync_response = self.guest_client.post(
            reverse('watch_party_sync', args=[self.movie.slug, code]),
            data=json.dumps({'playback_state': 'playing', 'current_time_seconds': 142}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(sync_response.status_code, 200)
        self.assertTrue(sync_response.json()['party']['can_control'])

    def test_state_payload_includes_recent_messages(self):
        create_payload = self.host_client.post(
            reverse('watch_party_create', args=[self.movie.slug]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        ).json()
        code = create_payload['party']['code']
        party = WatchParty.objects.get(code=code)
        WatchPartyMessage.objects.create(party=party, user=self.host, text='Listos para verla?')

        state_response = self.host_client.get(
            reverse('watch_party_state', args=[self.movie.slug, code]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(state_response.status_code, 200)
        state_payload = state_response.json()
        self.assertEqual(len(state_payload['messages']), 1)
        self.assertEqual(state_payload['messages'][0]['text'], 'Listos para verla?')

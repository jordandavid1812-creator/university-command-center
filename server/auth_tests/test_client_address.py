"""S0-01: throttle source address derivation (REMOTE_ADDR default, IPv6 /64, opt-in proxies)."""
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from accounts.models import AuthThrottle
from .base import AuthenticationCase, PASSWORD


def address(remote, forwarded=None):
    from accounts.throttling import client_address  # Lazy: baseline evidence runs without it.
    extra = {'REMOTE_ADDR': remote} if remote is not None else {}
    if forwarded is not None:
        extra['HTTP_X_FORWARDED_FOR'] = forwarded
    request = RequestFactory().post('/accounts/login/', **extra)
    if remote is None:
        request.META.pop('REMOTE_ADDR', None)
    return client_address(request)


class ClientAddressTests(SimpleTestCase):
    def test_remote_addr_is_default_and_forwarded_headers_are_ignored(self):
        self.assertEqual(address('192.0.2.10'), '192.0.2.10')
        self.assertEqual(address('192.0.2.10', '203.0.113.1'), '192.0.2.10')
        self.assertEqual(address('192.0.2.10', '203.0.113.1, 198.51.100.2'), '192.0.2.10')

    def test_ipv6_sources_are_grouped_by_64_prefix(self):
        self.assertEqual(address('2001:db8:1:2::1'), '2001:db8:1:2::/64')
        self.assertEqual(address('2001:db8:1:2:ffff:ffff:ffff:ffff'), '2001:db8:1:2::/64')
        self.assertEqual(address('2001:db8:1:3::1'), '2001:db8:1:3::/64')
        self.assertEqual(address('fe80::1%eth0'), 'fe80::/64')

    def test_ipv4_mapped_ipv6_uses_ipv4_bucket(self):
        self.assertEqual(address('::ffff:192.0.2.10'), '192.0.2.10')

    def test_missing_or_malformed_source_uses_one_conservative_bucket(self):
        for value in (None, '', 'not-an-ip', '999.1.1.1', 'x' * 500):
            self.assertEqual(address(value), 'unknown')

    @override_settings(UCC_TRUSTED_PROXIES=['10.0.0.0/8', '2001:db8:ffff::/48'])
    def test_trusted_proxy_uses_right_most_untrusted_forwarded_address(self):
        self.assertEqual(address('10.0.0.5', '203.0.113.7'), '203.0.113.7')
        # A client cannot choose its bucket by prepending forged entries.
        self.assertEqual(address('10.0.0.5', '198.51.100.99, 203.0.113.7'), '203.0.113.7')
        # Chained trusted proxies are skipped from the right.
        self.assertEqual(address('10.0.0.5', '203.0.113.7, 10.1.1.1'), '203.0.113.7')
        self.assertEqual(address('2001:db8:ffff::1', '2001:db8:aa:bb::5'), '2001:db8:aa:bb::/64')

    @override_settings(UCC_TRUSTED_PROXIES=['10.0.0.0/8'])
    def test_untrusted_peer_cannot_supply_forwarded_address(self):
        self.assertEqual(address('192.0.2.10', '203.0.113.7'), '192.0.2.10')

    @override_settings(UCC_TRUSTED_PROXIES=['10.0.0.0/8'])
    def test_trusted_proxy_with_missing_or_invalid_header_falls_back_to_proxy(self):
        self.assertEqual(address('10.0.0.5'), '10.0.0.5')
        self.assertEqual(address('10.0.0.5', ''), '10.0.0.5')
        self.assertEqual(address('10.0.0.5', '203.0.113.7, garbage'), '10.0.0.5')
        self.assertEqual(address('10.0.0.5', '10.2.2.2, 10.3.3.3'), '10.0.0.5')

    def test_trust_everything_and_invalid_proxy_configuration_fail_closed(self):
        for value in (['0.0.0.0/0'], ['::/0'], ['not-a-network'], '10.0.0.0/8'):
            with self.subTest(value=value), override_settings(UCC_TRUSTED_PROXIES=value):
                with self.assertRaises(ImproperlyConfigured):
                    address('10.0.0.5', '203.0.113.7')

    def test_operational_profiles_do_not_enable_trusted_proxies(self):
        from django.conf import settings
        self.assertEqual(tuple(getattr(settings, 'UCC_TRUSTED_PROXIES', ())), ())


class SharedSourceThrottleTests(AuthenticationCase):
    @override_settings(AUTH_RATE_LIMITS={'login': (2, 60)})
    def test_ipv6_rotation_within_one_64_shares_the_login_limit(self):
        for suffix in ('1', '2'):
            Client(REMOTE_ADDR=f'2001:db8:5:6::{suffix}').post(
                reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'})
        blocked = Client(REMOTE_ADDR='2001:db8:5:6::99').post(
            reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD})
        self.assertEqual(blocked.status_code, 429)
        other_network = Client(REMOTE_ADDR='2001:db8:5:7::1').post(
            reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD})
        self.assertEqual(other_network.status_code, 302)

    @override_settings(AUTH_RATE_LIMITS={'login': (2, 60)})
    def test_shared_ipv4_without_proxy_config_shares_one_bucket(self):
        # Accepted, documented limitation (S0-01): without a reviewed proxy list, students
        # behind one NAT address share the IP limit. The limit is not silently widened.
        self.assertEqual(self.login(Client(REMOTE_ADDR='192.0.2.50')).status_code, 302)
        self.assertEqual(self.login(Client(REMOTE_ADDR='192.0.2.50'), 'bravo').status_code, 302)
        self.assertEqual(self.login(Client(REMOTE_ADDR='192.0.2.50'), 'bravo').status_code, 429)
        self.assertEqual(self.login(Client(REMOTE_ADDR='192.0.2.51'), 'bravo').status_code, 302)

    @override_settings(AUTH_RATE_LIMITS={'login': (2, 60)})
    def test_rotating_distinct_sources_get_separate_ip_buckets(self):
        # IP limits alone cannot stop rotation across distinct addresses or /64 networks;
        # that is S0-02 (per-account limiting), deferred pending a lockout-safe design.
        statuses = {Client(REMOTE_ADDR=f'198.51.100.{index}').post(
            reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'}).status_code for index in range(1, 7)}
        self.assertEqual(statuses, {200})
        self.assertEqual(AuthThrottle.objects.using('auth').count(), 6)

    @override_settings(AUTH_RATE_LIMITS={'login': (2, 60)}, UCC_TRUSTED_PROXIES=['10.0.0.0/8'])
    def test_trusted_proxy_separates_students_but_not_forged_headers(self):
        proxy = '10.0.0.5'
        for _ in range(2):
            Client(REMOTE_ADDR=proxy).post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'},
                                           HTTP_X_FORWARDED_FOR='203.0.113.7')
        forged = Client(REMOTE_ADDR=proxy).post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'},
                                                HTTP_X_FORWARDED_FOR='198.51.100.1, 203.0.113.7')
        self.assertEqual(forged.status_code, 429)
        student = Client(REMOTE_ADDR=proxy).post(reverse('accounts:login'), {'username': 'bravo', 'password': PASSWORD},
                                                 HTTP_X_FORWARDED_FOR='203.0.113.8')
        self.assertEqual(student.status_code, 302)
        self.assertFalse(any('203.0.113' in row.bucket for row in AuthThrottle.objects.using('auth').all()))

from core.conf.utils import (
    map_industries,
    flatten,
    version_info,
    get_other_tenant_footers,
    get_tenant_level_ranges,
    get_level_key,
    get_next_level_key,
    in_top_level,
    get_level_info,
    get_dimension_level_info,
    get_detailed_survey_result_data,
    get_account_detail_data,
)
import mock
from djangae.test import TestCase
from collections import OrderedDict
from django.test import override_settings
from django.conf import settings
from core.tests.mocks import MOCKED_TENANTS, MOCKED_INTERNAL_TENANTS
from core.tests.mommy_recepies import make_survey, make_survey_result


class MapIndustriesTest(TestCase):
    """Test case for `core.conf.utils.map_industries` function."""

    def test_dictionary_flattened_correctly_single(self):

        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
        ])

        mapped_repr = map_industries(industries, None, {})

        self.assertEqual(len(mapped_repr), 1)
        label, parent_industry = mapped_repr.get('afs')
        self.assertIsNone(parent_industry)
        self.assertEqual(label, 'Accommodation and food service')

    def test_dictionary_flattened_correctly_nested(self):

        industries = OrderedDict([
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])

        mapped_repr = map_industries(industries, None, {})

        self.assertEqual(len(mapped_repr), 4)
        # all children of Education have Education as parent
        for category in ['edu-o', 'edu-pe', 'edu-se']:
            label, parent_industry = mapped_repr.get(category)
            self.assertEqual(parent_industry, 'edu')

        # root element does not have parent category
        label, cat = mapped_repr.get('edu')
        self.assertEqual(label, 'Education')
        self.assertEqual(cat, None)

    def test_dictionary_flattened_correctly_multiple(self):

        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
            ('co', ('Construction', None)),
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])

        mapped_repr = map_industries(industries, None, {})

        self.assertEqual(len(mapped_repr), 6)
        label, parent_industry = mapped_repr.get('afs')
        self.assertIsNone(parent_industry)
        self.assertEqual(label, 'Accommodation and food service')

    def test_prefix(self):
        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
            ('co', ('Construction', None)),
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])
        parent_prefix = 'root'

        mapped_repr = map_industries(industries, parent_prefix, {})

        self.assertEqual(len(mapped_repr), 6)
        label, parent_industry = mapped_repr.get('afs')
        self.assertIsNotNone(parent_industry)
        self.assertEqual(parent_industry, parent_prefix)
        self.assertEqual(label, 'Accommodation and food service')


class FlatIndustriesTest(TestCase):
    """Test case for `core.conf.utils.flat` function."""

    def test_dictionary_flattened_correctly_single(self):
        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
        ])

        flattened_repr = flatten(industries)

        self.assertEqual(len(flattened_repr), 1)

    def test_dictionary_flattened_correctly_single_nested(self):
        industries = OrderedDict([
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])

        flattened_repr = flatten(industries)

        self.assertEqual(len(flattened_repr), 3)
        for el in flattened_repr:
            key, label = el
            self.assertIn('Education -', label)

    def test_dictionary_flattened_correctly_multiple(self):
        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])

        flattened_expected = [
            ('afs', 'Accommodation and food service'),
            ('edu-o', 'Education - Other'),
            ('edu-pe', 'Education - Primary education'),
            ('edu-se', 'Education - Secondary education'),
        ]

        flattened_repr = flatten(industries)

        self.assertEqual(flattened_repr, flattened_expected)

    def test_dictionary_flattened_correctly_empty(self):
        industries = OrderedDict()

        flattened_repr = flatten(industries)

        self.assertEqual(len(flattened_repr), 0)

    def test_dictionary_flattened_correctly_leaf_only_false(self):
        industries = OrderedDict([
            ('afs', ('Accommodation and food service', None)),
            ('edu', ('Education', OrderedDict([
                ('edu-o', ('Other', None)),
                ('edu-pe', ('Primary education', None)),
                ('edu-se', ('Secondary education', None)),
            ]))),
        ])

        flattened_repr = flatten(industries, leaf_only=False)

        flattened_expected = [
            ('afs', 'Accommodation and food service'),
            ('edu-o', 'Education - Other'),
            ('edu-pe', 'Education - Primary education'),
            ('edu-se', 'Education - Secondary education'),
            ('edu', 'Education'),
        ]
        self.assertEqual(flattened_repr, flattened_expected)


class VersionInfoTest(TestCase):
    """Test for `core.utils.version_info` function."""

    @mock.patch('djangae.environment.is_development_environment', return_value=False)
    def production_domain_test(self, is_prod_mock):
        version, is_nightly, is_development, is_staging = version_info('somedomain')

        is_prod_mock.assert_called()
        self.assertFalse(is_development)
        self.assertIsNone(version)
        self.assertFalse(is_nightly)
        self.assertFalse(is_staging)

    @mock.patch('djangae.environment.is_development_environment', return_value=True)
    def localhost_domain_test(self, is_prod_mock):
        domain = 'localhost:8000'
        expected_version = 'localhost'
        version, is_nightly, is_development, is_staging = version_info(domain)
        self.assertEqual(version, expected_version)
        self.assertTrue(is_development)
        self.assertFalse(is_nightly)
        self.assertFalse(is_staging)

    @mock.patch('djangae.environment.is_development_environment', return_value=True)
    def localhost_domain_test_different_domain(self, is_prod_mock):
        domain = '0.0.0.0:8000'
        expected_version = 'localhost'
        version, is_nightly, is_development, is_staging = version_info(domain)
        self.assertEqual(version, expected_version)
        self.assertTrue(is_development)
        self.assertFalse(is_nightly)
        self.assertFalse(is_staging)

    @mock.patch('djangae.environment.is_development_environment', return_value=False)
    @mock.patch('djangae.environment.application_id', return_value='dmb-staging')
    def staging_domain_test(self, app_id_mock, is_prod_mock):
        domain = 'gweb-digitalmaturity-staging.appspot.com'
        expected_version = 'staging'
        version, is_nightly, is_development, is_staging = version_info(domain)
        self.assertEqual(version, expected_version)
        self.assertFalse(is_development)
        self.assertFalse(is_nightly)
        self.assertTrue(is_staging)

    @mock.patch('djangae.environment.is_development_environment', return_value=False)
    @mock.patch('djangae.environment.application_id', return_value='dmb-staging')
    def nightly_domain_test(self, app_id_mock, is_prod_mock):
        domain = 'ads-nightly-dot-gweb-digitalmaturity-staging.appspot.com'
        expected_version = 'ads-nightly'
        version, is_nightly, is_development, is_staging = version_info(domain)
        self.assertFalse(is_development)
        self.assertTrue(is_nightly)
        self.assertTrue(is_staging)
        self.assertEqual(version, expected_version)

    @mock.patch('djangae.environment.is_development_environment', return_value=False)
    @mock.patch('djangae.environment.application_id', return_value='dmb-staging')
    def tenant_not_nightly_domain_test(self, app_id_mock, is_prod_mock):
        domain = 'ads-dot-gweb-digitalmaturity-staging.appspot.com'
        expected_version = 'ads'
        version, is_nightly, is_development, is_staging = version_info(domain)
        self.assertEqual(version, expected_version)
        self.assertFalse(is_nightly)
        self.assertFalse(is_development)
        self.assertTrue(is_staging)


@override_settings(
    TENANTS=MOCKED_TENANTS,
)
class GetOtherTenantFootersTest(TestCase):
    """Test for `core.utils.get_other_tenant_footers` function."""

    def one_result_test(self):
        expected = [('Tenant 2 Footer Label', 'tenant2-slug')]
        got = get_other_tenant_footers('tenant1')

        self.assertListEqual(expected, got)

    @override_settings(
        TENANTS={
            'tenant1': {
                'slug': 'tenant1-slug',
                'in_dmb_footer': True,
                'footer_label': 'Tenant 1 Footer Label',
            },
            'tenant2': {
                'slug': 'tenant2-slug',
                'in_dmb_footer': True,
                'footer_label': 'Tenant 2 Footer Label',
            },
            'tenant3': {
                'slug': 'tenant3-slug',
                'in_dmb_footer': True,
                'footer_label': 'Tenant 3 Footer Label',
            },
        }
    )
    def mulitple_results_test(self):
        expected = [('Tenant 3 Footer Label', 'tenant3-slug'), ('Tenant 2 Footer Label', 'tenant2-slug')]
        got = get_other_tenant_footers('tenant1')

        self.assertListEqual(expected, got)

    @override_settings(
        TENANTS={
            'tenant1': {
                'slug': 'tenant1-slug',
                'in_dmb_footer': True,
                'footer_label': 'Tenant 1 Footer Label',
            },
            'tenant2': {
                'slug': 'tenant2-slug',
                'in_dmb_footer': True,
                'footer_label': 'Tenant 2 Footer Label',
            },
            'tenant3': {
                'slug': 'tenant3-slug',
                'in_dmb_footer': False,
                'footer_label': 'Tenant 3 Footer Label',
            },
        }
    )
    def not_in_dmb_test(self):
        expected = []
        got = get_other_tenant_footers('tenant3')

        self.assertListEqual(expected, got)

    def no_in_tenant_list_test(self):
        expected = []
        got = get_other_tenant_footers('tenant4')

        self.assertListEqual(expected, got)


@override_settings(
    TENANTS=MOCKED_TENANTS,
    INTERNAL_TENANTS=MOCKED_INTERNAL_TENANTS,
)
class GetLevelAttributesTest(TestCase):
    """Test for functions in `core.utils` for getting level-dependent properties/attributes."""

    def setUp(self):
        self.content_data = settings.TENANTS['tenant1']['CONTENT_DATA']
        self.level_ranges = self.content_data['level_ranges']

    def get_level_ranges_test(self):
        """Test that a tenants level ranges are assembled correctly"""
        # Check ranges are not empty.
        self.assertEqual(len(self.level_ranges), len(self.content_data['levels']))
        # Check ranges are formed correctly.
        for (level_min, level_max) in self.level_ranges:
            self.assertGreater(level_max, level_min)
            self.assertNotEqual(level_min, level_max)
        # Check that final range has max level as maximum
        self.assertEqual(self.level_ranges[-1][1], self.content_data['levels_max'])

    def get_level_key_test(self):
        """Tests that a score returns the correct level key"""
        levels = self.content_data['levels']
        # Check scores are classified correctly.
        for idx, level in enumerate(levels.keys()):
            if idx != 0:
                # If score is less than boundary the its the level before
                previous_level = levels.keys()[idx - 1]
                self.assertEqual(
                    get_level_key(self.level_ranges, level - 0.1),
                    previous_level
                )
            # If score is boundary then its the level
            self.assertEqual(
                get_level_key(self.level_ranges, level),
                level
            )
            if idx != len(levels.keys()) - 1:
                # If score is more than boundary but less than the one above its still the level
                self.assertEqual(
                    get_level_key(self.level_ranges, level + 0.1),
                    level
                )
        # Check scores outside ranges are classified correctly.
        self.assertEqual(
            get_level_key(self.level_ranges, self.level_ranges[0][0] - 100),
            self.level_ranges[0][0]
        )
        self.assertEqual(
            get_level_key(self.level_ranges, self.level_ranges[-1][1] + 100),
            self.level_ranges[-1][0]
        )

    def get_next_level_key_test(self):
        """Tests that the next level of a score is calculated correctly."""
        # Check that the next level of a non-top-level score is correct.
        self.assertEqual(
            get_next_level_key(self.level_ranges, self.level_ranges[0][0]),
            self.level_ranges[0][1]
        )
        # Check that the next level of a top-level score is correct.
        self.assertEqual(
            get_next_level_key(self.level_ranges, self.level_ranges[-1][1]),
            self.level_ranges[-1][0]
        )
        # Check scores outside ranges are classified correctly.
        self.assertEqual(
            get_level_key(self.level_ranges, self.level_ranges[0][0] - 100),
            self.level_ranges[0][0]
        )
        self.assertEqual(
            get_level_key(self.level_ranges, self.level_ranges[-1][1] + 100),
            self.level_ranges[-1][0]
        )

    def is_top_level_test(self):
        """Tests that a top score is classified correctly."""
        # Check that a top score is has the highest level.
        high_score = self.level_ranges[-1][1]
        level = get_level_key(self.level_ranges, high_score)
        self.assertTrue(in_top_level(self.level_ranges, level))

    def is_not_top_level_test(self):
        """Tests that a non-top score is classified correctly."""
        # Check that a low score does not have the highest level.
        low_score = self.level_ranges[0][0]
        level = get_level_key(self.level_ranges, low_score)
        self.assertFalse(in_top_level(self.level_ranges, level))

    def get_level_info_test(self):
        """Tests that a score returns the correct level information"""
        levels = self.content_data['levels']
        # Check correct level info is given for each level.
        for idx, level in enumerate(levels.keys()):
            level_info = get_level_info('tenant1', level)['levels']
            # Check current level info
            self.assertEqual(level, level_info['current']['value'])
            self.assertEqual(levels[level], level_info['current']['name'])
            self.assertEqual(self.content_data['level_descriptions'][level], level_info['current']['description'])
            # Check next level info
            if idx != len(levels.keys()) - 1:
                next_level = levels.keys()[idx + 1]
                next_level_info = get_level_info('tenant1', next_level)['levels']
                self.assertEqual(next_level, next_level_info['current']['value'])
                self.assertEqual(levels[next_level], next_level_info['current']['name'])
                self.assertEqual(
                    self.content_data['level_descriptions'][next_level],
                    next_level_info['current']['description']
                )

    def get_dimension_level_info_test(self):
        """Tests that a score returns the correct dimension level info"""
        levels = self.content_data['levels']
        dimension = 'dim1'
        # Check correct level info is given for each level.
        for idx, level in enumerate(levels.keys()):
            level_info = get_dimension_level_info('tenant1', dimension, level)['levels']
            # Check current level info
            self.assertEqual(level, level_info['current']['value'])
            self.assertEqual(levels[level], level_info['current']['name'])
            self.assertEqual(
                self.content_data['dimension_level_description'][dimension][level],
                level_info['current']['description']
            )
            # Check next level info
            if idx != len(levels.keys()) - 1:
                next_level = levels.keys()[idx + 1]
                next_level_info = get_dimension_level_info('tenant1', dimension, next_level)['levels']
                self.assertEqual(next_level, next_level_info['current']['value'])
                self.assertEqual(levels[next_level], next_level_info['current']['name'])
                self.assertEqual(
                    self.content_data['dimension_level_description'][dimension][next_level],
                    next_level_info['current']['description']
                )

    def get_detailed_survey_result_data_test(self):
        """Tests that a survey results data is correctly returned"""
        # Make fake survey results.
        survey = make_survey(tenant="tenant1")
        survey_result = make_survey_result(
            survey=survey,
            response_id='AAA',
            dmb=1,
            dmb_d={u"dim1": 0.4, u"dim2": 1.6}
        )
        # Get survey result data.
        survey_result_data = get_detailed_survey_result_data("tenant1", survey_result)
        # Check required fields are present
        self.assertIsNotNone(survey_result_data['date'])
        self.assertIsNotNone(survey_result_data['overall'])
        self.assertEqual(survey_result_data['overall']['value'], 1)

        for dimension in self.content_data['dimensions']:
            self.assertEqual(
                survey_result_data['dimensions'][dimension]['value'],
                survey_result.dmb_d[dimension]
            )
            self.assertEqual(
                survey_result_data['dimensions'][dimension]['name'],
                self.content_data['dimension_labels'][dimension]
            )
            self.assertEqual(survey_result_data['dimensions'][dimension]['inTopLevel'], False)
            self.assertIsNotNone(survey_result_data['dimensions'][dimension]['levels'])

    def get_empty_account_detail_data_test(self):
        """Tests that correct value is returned when a empty account is provided."""
        # Make fake survey results.
        survey = make_survey(tenant="tenant1")
        account_info, external_surveys, internal_surveys = get_account_detail_data("tenant1", survey)
        self.assertIsNotNone(account_info)
        self.assertListEqual(external_surveys, [])
        self.assertListEqual(internal_surveys, [])

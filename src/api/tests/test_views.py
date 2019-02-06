import json

from core.models import Survey
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.test import override_settings
import mock
from rest_framework import status
from rest_framework.test import APITestCase
from core.tests.mommy_recepies import make_survey, make_survey_result
from core.tests.mocks import INDUSTRIES
from core.aggregate import get_surveys_by_industry

User = get_user_model()


class SurveyTest(APITestCase):
    """Tests for `api.views.SurveyCompanyNameFromUIDView` view."""
    user_email = 'test@example.com'

    def setUp(self):
        user = User.objects.create(
            username='test1',
            email=self.user_email,
            password='pass',
        )

        self.client.force_authenticate(user)
        self.url = reverse('company_name')

    def test_fail_not_authenticated(self):
        """Ensure we can't hit the api if not authenticated."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_not_provide_company_name(self):
        """Get survey without providing `sid` in url should return 404."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_survey_exists(self):
        """Should return the `company_name` related to `sid` provided."""
        survey = make_survey()
        response = self.client.get(self.url, {
            "sid": survey.sid
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data.get('company_name'), survey.company_name)


class SurveyResultTest(APITestCase):
    """Tests for `api.views.SurveyResultsDetail` view."""
    user_email = 'test@example.com'

    def setUp(self):
        self.survey = make_survey(sid="92345123451234512345123451234512")

        self.survey_result = make_survey_result(
            survey=self.survey,
            response_id='AAA',
            dmb=1.0,
            dmb_d='{}'
        )

    def test_survey_result_not_found(self):
        url = reverse('survey_report', kwargs={'sid': '12345123451234512345123451234512'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cors_not_supported(self):
        url = reverse('survey_report', kwargs={'sid': self.survey.pk})
        headers = {
            'HTTP_ORIGIN': 'http://example.com',
            'HTTP_ACCESS_CONTROL_REQUEST_METHOD': 'POST',
            'HTTP_ACCESS_CONTROL_REQUEST_HEADERS': 'X-Requested-With',

        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.has_header('access-control-allow-origin'))


class SurveyDetailView(APITestCase):
    """Tests for `api.views.SurveyResultsDetail` view."""
    user_email = 'test@example.com'

    def setUp(self):
        self.survey = Survey.objects.create(company_name='test company', industry="re", country="IT")
        self.survey_result = make_survey_result(
            survey=self.survey,
            response_id='AAA',
            dmb=1.0,
            dmb_d='{}'
        )
        self.survey.last_survey_result = self.survey_result
        self.survey.save()
        self.url = reverse('survey_report', kwargs={'sid': self.survey.pk})

    def test_survey_result_found(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(float(response.data.get('survey_result').get('dmb')), self.survey_result.dmb)
        self.assertEqual(response.data.get('survey_result').get('response_id'), self.survey_result.response_id)

    def test_survey_result_not_found(self):
        url = reverse('survey_report', kwargs={'sid': '12345123451234512345123451234512'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cors_not_supported(self):
        url = reverse('survey_report', kwargs={'sid': self.survey.pk})
        headers = {
            'HTTP_ORIGIN': 'http://example.com',
            'HTTP_ACCESS_CONTROL_REQUEST_METHOD': 'POST',
            'HTTP_ACCESS_CONTROL_REQUEST_HEADERS': 'X-Requested-With',

        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.has_header('access-control-allow-origin'))

    def test_survey_result_get_last(self):
        survey_result = make_survey_result(
            survey=self.survey,
            response_id='BBB',
            dmb=2.0,
            dmb_d='{}'
        )
        self.survey.last_survey_result = survey_result
        self.survey.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(float(response.data.get('survey_result').get('dmb')), 2.0)
        self.assertEqual(response.data.get('survey_result').get('response_id'), 'BBB')

    def test_survey_does_not_have_last_result(self):
        survey = Survey.objects.create(company_name='test company no last result', industry="ic-o", country="IT")
        url = reverse('survey_report', kwargs={'sid': survey.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data.get('survey_result'))
        self.assertEqual(response.data.get('company_name'), 'test company no last result')


@override_settings(
    INDUSTRIES=INDUSTRIES
)
class CreateSurveyTest(APITestCase):
    """Tests for `api.views.CreateSurveyView` view."""

    def setUp(self):
        user = User.objects.create(
            username='test1',
            email='test@example.com',
            password='pass',
        )

        self.data = {
            'company_name': 'test company',
            'industry': 'ic-o',
            'country': 'GB',
        }

        self.client.force_authenticate(user)
        self.url = reverse('create_survey')

    def test_unauthenticated_user(self):
        """Unauthenticated users should be able to post."""
        self.client.force_authenticate(None)
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_required_fields_matched(self):
        """Posting data matching required parameters should succed."""
        response = self.client.post(self.url, self.data)
        post_response = response.data
        survey_db = Survey.objects.get(company_name=self.data.get('company_name'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(post_response.get('company_name'), survey_db.company_name)
        self.assertEqual(post_response.get('industry'), survey_db.industry)
        self.assertEqual(post_response.get('country'), survey_db.country)
        self.assertEqual(post_response.get('link'), survey_db.link)
        self.assertEqual(post_response.get('link_sponsor'), survey_db.link_sponsor)
        self.assertEqual(post_response.get('engagement_lead'), survey_db.engagement_lead)

    def test_required_fields_not_matched(self):
        """Posting data not matching required parameters should fail."""
        response = self.client.post(self.url, {'randomkey': 'randomvalue'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_industry_not_valid(self):
        """Posting data not matching required parameters should fail."""
        self.data['industry'] = 'invalid'
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(
    DIMENSIONS={
        'dimension_A': ['Q1', 'Q2'],
        'dimension_B': ['Q3'],
        'dimension_C': ['Q2'],
    },
    INDUSTRIES=INDUSTRIES,
    MIN_ITEMS_INDUSTRY_THRESHOLD=1,
    MIN_ITEMS_BEST_PRACTICE_THRESHOLD=2
)
class SurveyIndustryResultTest(APITestCase):
    """Tests for `api.views.SurveyResultsIndustryDetail` view."""

    def _assert_dict_in_list(self, d, list_to_ckeck):
        item_equal = []
        for l in list_to_ckeck:
            if not set(d.keys()) - set(l.keys()):
                equals = True
                for k, v in d.iteritems():
                    if v != l.get(k):
                        equals = False
                item_equal.append(equals)
        return any(item_equal)

    def setUp(self):
        self.survey_1_dmb_d = {
            'dimension_A': 2.0,
            'dimension_B': 2.0,
        }

        self.survey_2_dmb_d = {
            'dimension_A': 3.0,
            'dimension_C': 3.0,
        }

        self.survey_3_dmb_d = {
            'dimension_A': 1.0,
            'dimension_C': 1.0,
        }

        self.survey = Survey.objects.create(company_name='test company', industry='ic-o', country="IT")
        self.survey_2 = Survey.objects.create(company_name='test company 2', industry='ic-o', country="IT")

        survey_result = make_survey_result(
            survey=self.survey,
            response_id='AAA',
            dmb=1.0,
            dmb_d=json.dumps(self.survey_1_dmb_d)
        )

        survey_result_2 = make_survey_result(
            survey=self.survey_2,
            response_id='AAB',
            dmb=2.0,
            dmb_d=json.dumps(self.survey_2_dmb_d)
        )
        self.survey.last_survey_result = survey_result
        self.survey_2.last_survey_result = survey_result_2
        self.survey.save()
        self.survey_2.save()

    def test_industry_with_results(self):
        """
        When there are some results for an industry, and we are above minimum
        threshold, we expect some results back.
        """
        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print response_data_keys

        self.assertEqual(set(response_data_keys), {
            'industry',
            'dmb_industry',
            'dmb_bp_industry',
            'dmb',
            'dmb_d',
            'dmb_bp',
            'dmb_d_bp'
        })

    @mock.patch('core.qualtrics.benchmark.calculate_group_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.benchmark.calculate_best_practice', return_value=(None, None))
    def test_industry_with_results_multiple_survey_result_per_survey(self, mocked_best_practice, mocked_benchmark):
        """
        When a survey has multiple results, only the last one should be use
        to calculate the aggregated benchmarks.
        """
        survey_result_3 = make_survey_result(
            survey=self.survey_2,
            response_id='AAC',
            dmb=2.0,
            dmb_d=json.dumps(self.survey_3_dmb_d)
        )
        self.survey_2.last_survey_result = survey_result_3
        self.survey_2.save()

        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for key in ['industry', 'dmb', 'dmb_d', 'dmb_bp', 'dmb_d_bp']:
            self.assertIsNotNone(key in response_data_keys)

        # check mocked_benchmark is called with correct parameters
        mocked_benchmark.assert_called()
        args, _ = mocked_benchmark.call_args_list[0]
        dmb_d_list_arg = args[0]
        self.assertEqual(len(dmb_d_list_arg), 2)
        self.assertTrue(self._assert_dict_in_list(self.survey_1_dmb_d, dmb_d_list_arg))
        self.assertTrue(self._assert_dict_in_list(self.survey_3_dmb_d, dmb_d_list_arg))
        self.assertFalse(self._assert_dict_in_list(self.survey_2_dmb_d, dmb_d_list_arg))

        # check mocked_best_practice is called with correct parameters
        mocked_best_practice.assert_called()
        args, _ = mocked_best_practice.call_args_list[0]
        dmb_d_list_arg = args[0]
        self.assertEqual(len(dmb_d_list_arg), 2)
        self.assertTrue(self._assert_dict_in_list(self.survey_1_dmb_d, dmb_d_list_arg))
        self.assertTrue(self._assert_dict_in_list(self.survey_3_dmb_d, dmb_d_list_arg))
        self.assertFalse(self._assert_dict_in_list(self.survey_2_dmb_d, dmb_d_list_arg))

    def test_industry_without_results_no_industry(self):
        """When the is no industry with that specific name, we expect no results back."""
        url = reverse('survey_industry', kwargs={'industry': 'MKT'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(
        MIN_ITEMS_INDUSTRY_THRESHOLD=100,
        MIN_ITEMS_BEST_PRACTICE_THRESHOLD=100
    )
    def test_industry_without_results_not_enough_results(self):
        """
        If there are not enough results globally we expect no results back.
        """
        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # if industry is not found, or there are not enough results to calculate
        # dmb and dmb_d are returned as `None`
        self.assertEqual(set(response_data_keys), {
            'industry',
            'dmb_industry',
            'dmb_bp_industry',
            'dmb',
            'dmb_d',
            'dmb_bp',
            'dmb_d_bp'
        })

        # industry will be `None` because of the default value in root
        self.assertEqual(response.data.get('industry'), 'Information and Communication')
        self.assertIsNone(response.data.get('dmb_industry'))
        self.assertIsNone(response.data.get('dmb_bp_industry'))
        self.assertIsNone(response.data.get('dmb'))
        self.assertIsNone(response.data.get('dmb_d'))
        self.assertIsNone(response.data.get('dmb_bp'))
        self.assertIsNone(response.data.get('dmb_d_bp'))

    @mock.patch('core.qualtrics.benchmark.calculate_group_benchmark', return_value=(None, None))
    def test_last_survey_result_is_excluded_if_null(self, mocked_benchmark):
        """When last_survey_result is None, element is excluded from dmb calculation."""
        Survey.objects.create(company_name='test company 3', industry='ic-o', country="IT", last_survey_result=None)

        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        print response.data

        self.assertEqual(set(response_data_keys), {
            'industry',
            'dmb_industry',
            'dmb_bp_industry',
            'dmb',
            'dmb_d',
            'dmb_bp',
            'dmb_d_bp'
        })

        mocked_benchmark.assert_called()

        call = mocked_benchmark.call_args_list[0]
        args, _ = call

        dmb_d_list_arg = args[0]
        self.assertEqual(len(dmb_d_list_arg), 2)
        self.assertTrue(self._assert_dict_in_list(self.survey_1_dmb_d, dmb_d_list_arg))
        self.assertTrue(self._assert_dict_in_list(self.survey_2_dmb_d, dmb_d_list_arg))
        self.assertFalse(self._assert_dict_in_list(self.survey_3_dmb_d, dmb_d_list_arg))

    @override_settings(
        MIN_ITEMS_INDUSTRY_THRESHOLD=10,
        MIN_ITEMS_BEST_PRACTICE_THRESHOLD=2
    )
    @mock.patch('core.qualtrics.benchmark.calculate_group_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.benchmark.calculate_best_practice', return_value=(None, None))
    def test_industry_not_enough_results_group_benchmark(self, mocked_best_practice, mocked_benchmark):
        """When there are not enough results, it will return the global industry calculation."""
        Survey.objects.create(company_name='test company 3', industry='ic-o', country="IT", last_survey_result=None)

        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(set(response_data_keys), {
            'industry',
            'dmb_industry',
            'dmb_bp_industry',
            'dmb',
            'dmb_d',
            'dmb_bp',
            'dmb_d_bp'
        })

        self.assertEqual(mocked_benchmark.call_count, 0)
        self.assertEqual(mocked_best_practice.call_count, 1)

        call = mocked_best_practice.call_args_list[0]
        args, _ = call

        dmb_d_list_arg = args[0]
        self.assertEqual(len(dmb_d_list_arg), 2)
        self.assertTrue(self._assert_dict_in_list(self.survey_1_dmb_d, dmb_d_list_arg))
        self.assertTrue(self._assert_dict_in_list(self.survey_2_dmb_d, dmb_d_list_arg))
        self.assertFalse(self._assert_dict_in_list(self.survey_3_dmb_d, dmb_d_list_arg))

        self.assertIsNone(response.data['dmb_industry'])
        self.assertEqual(response.data['industry'], 'Information and Communication')
        self.assertEqual(response.data['dmb_bp_industry'], 'all')

    @override_settings(
        MIN_ITEMS_INDUSTRY_THRESHOLD=10,
        MIN_ITEMS_BEST_PRACTICE_THRESHOLD=5
    )
    @mock.patch('core.qualtrics.benchmark.calculate_group_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.benchmark.calculate_best_practice', return_value=(None, None))
    def test_industry_not_enough_results_no_best_practice(self, mocked_best_practice, mocked_benchmark):
        """When there are not enough results, it will return the global industry calculation."""
        Survey.objects.create(company_name='test company 3', industry='edu-o', country="IT", last_survey_result=None)

        url = reverse('survey_industry', kwargs={'industry': 'ic'})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(set(response_data_keys), {
            'industry',
            'dmb_industry',
            'dmb_bp_industry',
            'dmb',
            'dmb_d',
            'dmb_bp',
            'dmb_d_bp'
        })

        self.assertEqual(mocked_benchmark.call_count, 0)
        self.assertEqual(mocked_best_practice.call_count, 0)

    @override_settings(
        MIN_ITEMS_INDUSTRY_THRESHOLD=2,
        MIN_ITEMS_BEST_PRACTICE_THRESHOLD=3
    )
    @mock.patch('api.views.get_surveys_by_industry', autospec=True, return_value=get_surveys_by_industry('ic-o', 2))
    def test_industry_fallbacks_average(self, get_surveys_by_industry_mock):
        """Views use get_survey_by_industry to get the fallbacked industry and related surveys"""

        url = reverse('survey_industry', kwargs={'industry': 'ic-o'})
        self.client.get(url)

        self.assertEqual(get_surveys_by_industry_mock.call_count, 2)
        self.assertEqual(get_surveys_by_industry_mock.call_count, 2)
        self.assertEqual(get_surveys_by_industry_mock.call_args_list, [mock.call('ic-o', 2), mock.call('ic-o', 3)])


class SurveyResultDetailView(APITestCase):
    """Tests for `api.views.SurveyResultDetailView` view."""
    user_email = 'test@example.com'

    def setUp(self):
        self.survey = make_survey(company_name='test company', country="IT")
        self.survey_result = make_survey_result(
            survey=self.survey,
            response_id='R_3ozFIv81JgJ5zok',
            dmb=1.0,
            dmb_d='{}'
        )
        self.survey.last_survey_result = self.survey_result
        self.survey.save()

    def test_survey_result_found(self):

        url = reverse('survey_result_report', kwargs={'response_id': self.survey_result.response_id})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response_data_keys), {
            'company_name',
            'industry',
            'industry_name',
            'country_name',
            'survey_result',
            'created_at',
        })

    def test_survey_result_not_found(self):
        url = reverse('survey_result_report', kwargs={'response_id': 'AAA'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_survey_result_found_multi_result(self):
        survey_result = make_survey_result(
            survey=self.survey,
            response_id='R_22222',
            dmb=2.0,
            dmb_d='{}'
        )

        url = reverse('survey_result_report', kwargs={'response_id': survey_result.response_id})
        response = self.client.get(url)
        response_data_keys = response.data.keys()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('company_name'), 'test company')
        self.assertAlmostEqual(float(response.data.get('survey_result').get('dmb')), 2.0)

        self.assertEqual(set(response_data_keys), {
            'company_name',
            'industry',
            'industry_name',
            'country_name',
            'survey_result',
            'created_at',
        })

    def test_survey_result_no_survey_attached(self):
        survey_result = make_survey_result(
            response_id='R_22222',
            dmb=2.0,
            dmb_d='{}'
        )

        url = reverse('survey_result_report', kwargs={'response_id': survey_result.response_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

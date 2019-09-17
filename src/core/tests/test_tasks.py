# encoding=utf-8
import mock

from core.models import Survey, SurveyResult, SurveyDefinition, IndustryBenchmark
from core.tasks import (
    _get_results,
    send_emails_for_new_reports,
    is_valid_email,
    _create_survey_results,
    _create_survey_result,
    _create_internal_result,
    generate_csv_export,
    _update_responses_with_text,
    _get_definition,
    sync_qualtrics,
    calculate_industry_benchmark,
    render_email_template,
    export_tenant_data,
)
from djangae.test import TestCase
from mocks import (
    get_mocked_results,
    MOCKED_DIMENSIONS,
    get_mocked_results_unfished,
    get_survey_definition,
    MOCKED_TENANTS,
    MOCKED_INTERNAL_TENANTS,
)
from mommy_recepies import make_user, make_survey, make_survey_result, make_survey_definition, make_survey_with_result
from core.qualtrics.exceptions import FetchResultException
from django.test import override_settings
from django.utils import dateparse
from django.utils.timezone import make_aware
import pytz
from collections import OrderedDict
from django.conf import settings
from django.template.loader import get_template
import unittest


@override_settings(
    DIMENSIONS=MOCKED_DIMENSIONS,
    TENANTS=MOCKED_TENANTS,
)
class sync_qualtricsTestCase(TestCase):
    """
    Returns `True` if the user is set in the admin console and is a googler
    `False` otherwise.
    """
    @mock.patch('core.tasks._get_definition', return_value='something')
    @mock.patch('core.tasks._get_results', return_value='something')
    def test_syncs_def_and_results(self, get_result_mock, get_survey_definition_mock):
        sync_qualtrics()
        self.assertEqual(get_survey_definition_mock.call_count, len(MOCKED_TENANTS.keys()))

        all_calls = get_survey_definition_mock.call_args_list

        for args, kwargs in all_calls:
            self.assertEqual(len(args), 2)
            tenant, qualtrics_id = args
            self.assertIsNotNone(tenant)
            self.assertTrue(tenant in MOCKED_TENANTS.keys())

        self.assertEqual(get_result_mock.call_count, len(MOCKED_TENANTS.keys()))

        all_calls = get_result_mock.call_args_list

        args, kwargs = all_calls[0]
        self.assertEqual(len(args), 3)
        self.assertIsNotNone(args[0])

    @mock.patch('core.tasks._get_definition', return_value=None)
    @mock.patch('core.tasks._get_results', return_value='something')
    def test_syncs_def_fails(self, get_result_mock, get_survey_definition_mock):
        sync_qualtrics()
        self.assertEqual(get_survey_definition_mock.call_count, len(MOCKED_TENANTS.keys()))
        self.assertEqual(get_result_mock.call_count, 0)

    @override_settings(
        INTERNAL_TENANTS=MOCKED_INTERNAL_TENANTS,
    )
    @mock.patch('core.tasks._get_definition', return_value='something')
    @mock.patch('core.tasks._get_results', return_value='something')
    def test_correct_survey_definition(self, get_result_mock, get_survey_definition_mock):
        """Check that survey definitions are found correctly for internal and external tenants using the tenants' key"""
        sync_qualtrics()
        # Check the number of calls is equal to the number of internal and external tenants
        self.assertEqual(
            get_survey_definition_mock.call_count,
            len(MOCKED_TENANTS.keys()) + len(MOCKED_INTERNAL_TENANTS.keys())
        )
        # Get all the calls and args
        all_calls = get_survey_definition_mock.call_args_list
        for args, kwargs in all_calls:
            # Check tenant and sid are passed
            self.assertEqual(len(args), 2)
            # Check tenant is not null
            tenant, qualtrics_id = args
            self.assertIsNotNone(tenant)
            # Check that if a tenant has an internal version that an additonal call
            # was made using the internal tenant key and correct qualtrics ID.
            if MOCKED_INTERNAL_TENANTS.get(tenant):
                get_survey_definition_mock.assert_any_call(
                    MOCKED_INTERNAL_TENANTS[tenant]['key'],
                    MOCKED_INTERNAL_TENANTS[tenant]['QUALTRICS_SURVEY_ID']
                )
            elif MOCKED_TENANTS.get(tenant):
                # Check tenant has called the get definition with the correct params.
                get_survey_definition_mock.assert_any_call(
                    MOCKED_TENANTS[tenant]['key'],
                    MOCKED_TENANTS[tenant]['QUALTRICS_SURVEY_ID']
                )


@override_settings(
    DIMENSIONS=MOCKED_DIMENSIONS
)
class GetResultsTestCase(TestCase):
    """Tests for get_result function"""

    def setUp(self):
        self.tenant = MOCKED_TENANTS['tenant1']

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch(
        'core.qualtrics.download.fetch_results',
        side_effect=[get_mocked_results(), get_mocked_results(text=True)]
    )
    def test_new_survey_first_time_download(self, download_mock, send_email_mock):
        """Test surveys are downloaded for the first time.

        We're assuming that all the Surveys have been created previously and
        SurveyResults are created only if the survey has been completed (`Finished`
        flag set to `1`).
        """
        make_survey()
        make_survey()
        make_survey()

        self.assertEqual(Survey.objects.count(), 3)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        self.assertEqual(Survey.objects.count(), 3)
        self.assertEqual(SurveyResult.objects.count(), 3)

        self.assertTrue(download_mock.called)
        self.assertEqual(download_mock.call_count, 2)
        all_calls = download_mock.call_args_list
        # first call to get all results it should have started_after = None
        args, kwargs = all_calls[0]
        self.assertIsNone(kwargs.get('started_after'))
        # second call to get all text results it should have started_after = None and text `True`
        args, kwargs = all_calls[1]
        self.assertIsNone(kwargs.get('started_after'))
        self.assertEqual(kwargs.get('text'), True)

        self.assertTrue(send_email_mock.called)
        args, kwargs = send_email_mock.call_args
        self.assertEqual(len(args[0]), 3)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch(
        'core.qualtrics.download.fetch_results',
        side_effect=[get_mocked_results(), get_mocked_results(text=True)]
    )
    def test_surveys_results_and_survey_updated(self, download_mock, send_email_mock):
        """Survey results are saved anyway (if survey has been completed), regardless Survey's related object exists."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        survey = make_survey(sid=1)
        make_survey()
        make_survey()

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        survey_1 = Survey.objects.get(pk=survey.sid)

        # Last result is updated.
        self.assertIsNotNone(survey_1.last_survey_result)

        self.assertTrue(download_mock.called)
        self.assertEqual(download_mock.call_count, 2)
        all_calls = download_mock.call_args_list
        # first call to get all results it should have started_after = None
        args, kwargs = all_calls[0]
        self.assertIsNone(kwargs.get('started_after'))
        # second call to get all text results it should have started_after = None and text `True`
        args, kwargs = all_calls[1]
        self.assertIsNone(kwargs.get('started_after'))
        self.assertEqual(kwargs.get('text'), True)

        # send_emails_for_new_reports is called
        self.assertTrue(send_email_mock.called)
        args, kwargs = send_email_mock.call_args
        self.assertEqual(len(args[0]), 3)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch(
        'core.qualtrics.download.fetch_results',
        side_effect=[get_mocked_results(), get_mocked_results(text=True)]
    )
    def test_surveys_results_are_always_saved(self, download_mock, send_email_mock):
        """Survey results are saved anyway (if survey has been completed), regardless Survey's related object exists."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 3)

        # send_emails_for_new_reports is called
        self.assertTrue(send_email_mock.called)
        args, kwargs = send_email_mock.call_args
        self.assertEqual(len(args[0]), 3)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch(
        'core.qualtrics.download.fetch_results',
        side_effect=[
            get_mocked_results(started_after=dateparse.parse_datetime('2018-07-31 14:16:06')),
            get_mocked_results(started_after=dateparse.parse_datetime('2018-07-31 14:16:06'), text=True)]
    )
    def test_partial_download_existing_survey(self, download_mock, send_email_mock):
        # survey has been created on datastore
        survey = make_survey()
        make_survey()
        make_survey()

        # only survey result with date after 2018-07-31 14:16:06 has been downloaded
        string_survey_started_at = '2018-07-31 14:16:06'
        survey_started_at = make_aware(dateparse.parse_datetime(string_survey_started_at), pytz.timezone('US/Mountain'))
        make_survey_result(survey=survey, started_at=string_survey_started_at)

        self.assertEqual(Survey.objects.count(), 3)
        self.assertEqual(SurveyResult.objects.count(), 1)

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        # no new Survey objects are created
        self.assertEqual(Survey.objects.count(), 3)

        self.assertEqual(download_mock.call_count, 2)
        all_calls = download_mock.call_args_list
        # first call to get all results it should have started_after = None
        args, kwargs = all_calls[0]
        self.assertIsNotNone(kwargs.get('started_after'))
        self.assertEqual(kwargs.get('started_after'), survey_started_at)
        # second call to get all text results it should have started_after = None and text `True`
        args, kwargs = all_calls[1]
        self.assertIsNotNone(kwargs.get('started_after'))
        self.assertEqual(kwargs.get('started_after'), survey_started_at)
        self.assertEqual(kwargs.get('text'), True)

        # only two new items will be created
        self.assertEqual(SurveyResult.objects.count(), 3)

        # send_emails_for_new_reports is called
        self.assertTrue(send_email_mock.called)
        args, kwargs = send_email_mock.call_args
        self.assertEqual(len(args[0]), 2)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch('core.qualtrics.download.fetch_results')
    def test_fetch_results_fails(self, download_mock, send_email_mock):
        exception_body = {
            'meta': {
                'httpStatus': 400,
                'error': {
                    'errorMesasge': 'some error'
                }
            }
        }
        download_mock.side_effect = FetchResultException(exception_body)

        string_survey_started_at = '2018-07-31 14:16:06'
        survey_started_at = make_aware(dateparse.parse_datetime(string_survey_started_at), pytz.timezone('US/Mountain'))
        survey = make_survey()
        make_survey_result(survey=survey, started_at=string_survey_started_at)
        self.assertEqual(SurveyResult.objects.count(), 1)

        with mock.patch('core.tasks._create_survey_results') as survey_result_mock:
            _get_results(self.tenant, make_survey_definition(), _create_survey_result)
            survey_result_mock.assert_not_called()
            download_mock.assert_called_once_with(self.tenant['QUALTRICS_SURVEY_ID'], started_after=survey_started_at)
            self.assertEqual(Survey.objects.count(), 1)
            self.assertEqual(SurveyResult.objects.count(), 1)

            # send_emails_for_new_reports is not called
            self.assertFalse(send_email_mock.called)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch('core.qualtrics.download.fetch_results', return_value=get_mocked_results_unfished())
    def test_unfinished_surveys_download(self, download_mock, send_email_mock):
        """Test surveys downloaded are unfinished.

        Unfinished surveys should not be saved as Survey, and the email sending
        should not be triggered.
        """
        make_survey()
        make_survey()
        make_survey()

        self.assertEqual(Survey.objects.count(), 3)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        self.assertEqual(Survey.objects.count(), 3)
        self.assertEqual(SurveyResult.objects.count(), 0)

        # send_emails_for_new_reports is not called
        self.assertFalse(send_email_mock.called)

    @mock.patch('core.tasks.send_emails_for_new_reports')
    @mock.patch(
        'core.qualtrics.download.fetch_results',
        side_effect=[get_mocked_results(), get_mocked_results(text=True)]
    )
    def test_new_fetch_results_is_called_with_survey_id(self, download_mock, send_email_mock):
        """Test fetch_results is always called with survey_id as positional paramenter."""
        make_survey()
        make_survey()
        make_survey()

        _get_results(self.tenant, make_survey_definition(), _create_survey_result)

        self.assertTrue(download_mock.called)
        self.assertEqual(download_mock.call_count, 2)
        all_calls = download_mock.call_args_list
        # first call to get all results it should have started_after = None
        args, kwargs = all_calls[0]

        self.assertIsNone(kwargs.get('started_after'))
        self.assertEqual(len(args), 1)
        self.assertIsNotNone(args[0])
        # second call to get all text results it should have started_after = None and text `True`
        args, kwargs = all_calls[1]
        self.assertIsNone(kwargs.get('started_after'))
        self.assertEqual(len(args), 1)
        self.assertIsNotNone(args[0])
        self.assertEqual(kwargs.get('text'), True)

        self.assertTrue(send_email_mock.called)
        args, kwargs = send_email_mock.call_args
        self.assertEqual(len(args[0]), 3)


class EmailValidatorTestCase(TestCase):
    """Tests for is_valid_email function."""

    def test_invalid_emails(self):
        self.assertFalse(is_valid_email(None))
        self.assertFalse(is_valid_email(''))
        self.assertFalse(is_valid_email('astring'))
        self.assertFalse(is_valid_email('email@example.com\n'))
        self.assertFalse(is_valid_email('email@example'))
        self.assertFalse(is_valid_email('email\n@example.com'))
        self.assertFalse(is_valid_email('email@example\n.com'))

    def test_valid_emails(self):
        self.assertTrue(is_valid_email('email@example.com'))
        self.assertTrue(is_valid_email('email123@example.com'))


@override_settings(
    TENANTS=MOCKED_TENANTS,
    NEWS='tenant2',
    RETAIL='tenant3',
)
class CreateSurveyResultTestCase(TestCase):
    """Tests for _create_survey_results function, when survey has been completed."""
    def setUp(self):
        responses_values = get_mocked_results().get('responses')
        responses_text = get_mocked_results(text=True).get('responses')
        self.responses = _update_responses_with_text(responses_values, responses_text).values()
        self.response_ids = [response['value'].get('ResponseID') for response in self.responses
                             if response['value'].get('Finished') == '1']
        self.survey_definition = make_survey_definition()
        self.tenant = settings.TENANTS['tenant1']

    def test_survey_result_created(self):
        """`SurveyResult` is always created."""
        survey = make_survey(pk=1)
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        # Test result have survey_id set but not internal_survey_id
        for survey_result in got_survey_results:
            self.assertIsNone(survey_result.internal_survey_id)
            self.assertIsNotNone(survey_result.survey_id)

        self.assertEqual(Survey.objects.count(), 1)
        # mocked data contains 3 finished survey results
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertTrue(len(got_ids) == len(self.response_ids))
        for response_id in self.response_ids:
            self.assertTrue(response_id in got_ids)

        # mocked survey has a internal response and no external responses
        self.assertEqual(survey.internal_results.count(), 0)
        self.assertEqual(survey.survey_results.count(), 1)

    def test_survey_result_created_no_survey_found(self):
        """When a Survey is not found, `SurveyResult` is created anyway."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertTrue(len(got_ids) == len(self.response_ids))
        for response_id in self.response_ids:
            self.assertTrue(response_id in got_ids)

    def test_survey_result_not_duplicated(self):
        """When a SurveyResult with a specific response_id already exists, it won't be created again."""
        # presave finished surveys
        for response in self.responses:
            response_value = response['value']
            if response_value.get('Finished') == '1':
                make_survey_result(
                    started_at=response_value.get('StartDate'),
                    response_id=response_value.get('ResponseID'))

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 3)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        self.assertEqual(Survey.objects.count(), 0)
        # no new results are created
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertEqual(len(got_ids), 0)

    @mock.patch('core.qualtrics.benchmark.calculate_response_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.question.get_question')
    @mock.patch('core.qualtrics.question.data_to_questions_text')
    @mock.patch('core.qualtrics.question.data_to_questions')
    def test__create_survey_results_call_correctly_underlying_functions(
        self, data_to_questions_mock, data_to_questions_text_mock, get_question_mock, calculate_response_benchmark_mock
    ):
        """_create_survey_results is calling with correct parameters the underlying functions."""
        make_survey()
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)

        data_to_questions_mock.assert_called()
        data_to_questions_text_mock.assert_called()
        calculate_response_benchmark_mock.assert_called()
        # expected get_question function not to be called, if tenant is not NEWS
        get_question_mock.assert_not_called()

    @mock.patch('core.qualtrics.benchmark.calculate_response_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.question.get_question', return_value=1)
    @mock.patch('core.qualtrics.question.data_to_questions_text')
    @mock.patch('core.qualtrics.question.data_to_questions')
    def test__create_survey_results_call_correctly_underlying_functions_news_tenant(
        self, data_to_questions_mock, data_to_questions_text_mock, get_question_mock, calculate_response_benchmark_mock
    ):
        """
        _create_survey_results is calling with correct parameters the underlying functions when the tenant is NEWS.
        """
        tenant = settings.TENANTS['tenant2']
        make_survey()
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, tenant, _create_survey_result)

        data_to_questions_mock.assert_called()
        data_to_questions_text_mock.assert_called()
        calculate_response_benchmark_mock.assert_called()
        get_question_mock.assert_called()

        all_calls = calculate_response_benchmark_mock.call_args_list
        args, kwargs = all_calls[0]
        self.assertIsNotNone(kwargs.get('dimensions_weights'))
        self.assertDictEqual(kwargs.get('dimensions_weights'), tenant['DIMENSIONS_WEIGHTS'][1])

    @mock.patch('core.qualtrics.benchmark.calculate_response_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.question.get_question', return_value=1)
    @mock.patch('core.qualtrics.question.data_to_questions_text')
    @mock.patch('core.qualtrics.question.data_to_questions')
    def test__create_survey_results_call_correctly_underlying_functions_retail_tenant(
        self, data_to_questions_mock, data_to_questions_text_mock, get_question_mock, calculate_response_benchmark_mock
    ):
        """
        _create_survey_results is calling with correct parameters the underlying functions when the tenant is RETAIL.
        """
        tenant = settings.TENANTS['tenant3']
        make_survey()
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, tenant, _create_survey_result)

        data_to_questions_mock.assert_called()
        data_to_questions_text_mock.assert_called()
        calculate_response_benchmark_mock.assert_called()
        get_question_mock.assert_not_called()

        all_calls = calculate_response_benchmark_mock.call_args_list
        args, kwargs = all_calls[0]
        self.assertIsNotNone(kwargs.get('dimensions_weights'))
        self.assertDictEqual(kwargs.get('dimensions_weights'), tenant['DIMENSIONS_WEIGHTS'])


@override_settings(
    TENANTS=MOCKED_TENANTS,
    INTERNAL_TENANTS=MOCKED_INTERNAL_TENANTS,
)
class CreateInternalSurveyResultTestCase(TestCase):
    """Tests for _create_survey_results function, when an internal survey has been completed."""
    def setUp(self):
        responses_values = get_mocked_results().get('responses')
        responses_text = get_mocked_results(text=True).get('responses')
        self.responses = _update_responses_with_text(responses_values, responses_text).values()
        self.response_ids = [response['value'].get('ResponseID') for response in self.responses
                             if response['value'].get('Finished') == '1']
        self.tenant = settings.INTERNAL_TENANTS['tenant1']
        self.survey_definition = make_survey_definition(tenant=self.tenant['key'])

    def test_internal_survey_result_created(self):
        """`SurveyResult` is always created and correctly links to survey if it exists."""
        survey = make_survey(sid=1)
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_internal_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        # Test result have internal_survey_id set but not survey_id
        for survey_result in got_survey_results:
            self.assertIsNotNone(survey_result.internal_survey_id)
            self.assertIsNone(survey_result.survey_id)

        self.assertEqual(Survey.objects.count(), 1)
        # mocked data contains 3 finished survey results
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertTrue(len(got_ids) == len(self.response_ids))
        for response_id in self.response_ids:
            self.assertTrue(response_id in got_ids)

        # mocked survey has a internal response and no external responses
        self.assertEqual(survey.internal_results.count(), 1)
        self.assertEqual(survey.survey_results.count(), 0)

    def test_internal_survey_result_created_no_survey_found(self):
        """When a Survey is not found, `SurveyResult` is created anyway."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_internal_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertTrue(len(got_ids) == len(self.response_ids))
        for response_id in self.response_ids:
            self.assertTrue(response_id in got_ids)

    def test_internal_survey_result_not_duplicated(self):
        """When a SurveyResult with a specific response_id already exists, it won't be created again."""
        # presave finished surveys
        for response in self.responses:
            response_value = response['value']
            if response_value.get('Finished') == '1':
                make_survey_result(
                    started_at=response_value.get('StartDate'),
                    response_id=response_value.get('ResponseID'))

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 3)

        got_survey_results = _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_internal_result)  # noqa
        got_ids = [result.response_id for result in got_survey_results]

        # Test result have internal_survey_id set but not survey_id
        for survey_result in got_survey_results:
            self.assertIsNone(survey_result.internal_survey_id)
            self.assertIsNone(survey_result.survey_id)

        self.assertEqual(Survey.objects.count(), 0)
        # no new results are created
        self.assertEqual(SurveyResult.objects.count(), 3)
        self.assertTrue(isinstance(got_ids, list))
        self.assertEqual(len(got_ids), 0)

    @mock.patch('core.qualtrics.benchmark.calculate_response_benchmark', return_value=(None, None))
    @mock.patch('core.qualtrics.question.get_question')
    @mock.patch('core.qualtrics.question.data_to_questions_text')
    @mock.patch('core.qualtrics.question.data_to_questions')
    def test_create_internal_survey_results_call_correctly_underlying_functions(
        self, data_to_questions_mock, data_to_questions_text_mock, get_question_mock, calculate_response_benchmark_mock
    ):
        """_create_survey_results is calling with correct parameters the underlying functions."""
        make_survey()
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_internal_result)

        data_to_questions_mock.assert_called()
        data_to_questions_text_mock.assert_called()
        calculate_response_benchmark_mock.assert_called()
        # expected get_question function not to be called, if tenant is not NEWS
        get_question_mock.assert_not_called()


@override_settings(
    TENANTS=MOCKED_TENANTS
)
class CreateSurveyResultUnfinishedTestCase(TestCase):
    """Tests for _create_survey_results function, when survey has not been completed."""
    def setUp(self):
        responses_values = get_mocked_results_unfished().get('responses')
        responses_text = get_mocked_results_unfished(text=True).get('responses')
        self.responses = _update_responses_with_text(responses_values, responses_text).values()
        self.survey_definition = make_survey_definition()
        self.tenant = settings.TENANTS['tenant1']

    def test_survey_result_created(self):
        """`SurveyResult` is always created."""
        make_survey()
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)

        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(SurveyResult.objects.count(), 0)

    def test_survey_result_created_no_survey_found(self):
        """When a Survey is not found, `SurveyResult` is created anyway."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

    def test_survey_result_not_created_for_not_finished_survey(self):
        """When a Survey is not completed, `SurveyResult` is not created."""
        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)

        # Asserting we're logging a message if survey is not completed
        with mock.patch('logging.warning') as logging_mock:
            _create_survey_results(self.responses, self.survey_definition, self.tenant, _create_survey_result)
            self.assertTrue(logging_mock.called)

        self.assertEqual(Survey.objects.count(), 0)
        self.assertEqual(SurveyResult.objects.count(), 0)


class SendEmailTestCase(TestCase):
    """Tests for send_emails_for_new_reports function."""
    def setUp(self):
        make_survey(sid='1')
        make_survey(sid='2')

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_not_send_to_invalid(self, email_mock):
        """`SurveyResult` email is not sent, because `to` field is invalid."""
        email_list = [
            ('invalidemail', 'test@example.com', '1', 'en')
        ]

        send_emails_for_new_reports(email_list)
        email_mock.assert_not_called()

        # if 'to' is not set, then don't send email
        email_list = [
            (None, 'test@example.com', '1', 'en')
        ]

        send_emails_for_new_reports(email_list)
        email_mock.assert_not_called()

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_is_correctly_sent_bcc_invalid(self, email_mock):
        """`SurveyResult` email is sent to `to` recipient, but not to `bbc` because `bcc` field is invalid."""
        email_list = [
            ('test@example.com', 'invalidemail', '1', 'en')
        ]

        send_emails_for_new_reports(email_list)
        self.assertEqual(email_mock.call_args_list, [mock.call()])

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_is_correctly_sent_with_bcc(self, email_mock):
        """`SurveyResult` email is sent correctly."""
        email_list = [
            ('test@example.com', 'test@example.com', '1', 'en')
        ]

        send_emails_for_new_reports(email_list)
        self.assertEqual(email_mock.call_args_list, [mock.call()])

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_is_correctly_sent_no_bcc(self, email_mock):
        """`SurveyResult` email is sent to `to` recipient, but not to `bbc` because `bcc` field is invalid."""
        email_list = [
            ('test@example.com', None, '1', 'en')
        ]

        send_emails_for_new_reports(email_list)
        self.assertEqual(email_mock.call_args_list, [mock.call()])

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_is_correctly_sent_multiple_emails(self, email_mock):
        """`SurveyResult` email is sent correctly, when email_list has more than one element."""
        email_list = [
            ('test@example.com', 'test@example.com', '1', 'en'),
            ('test2@example.com', 'test3@example.com', '2', 'es')
        ]

        send_emails_for_new_reports(email_list)
        self.assertEqual(email_mock.call_count, 2)

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    def test_email_is_not_sent_if_surevy_does_not_exist(self, email_mock):
        """`SurveyResult` email is not sent, when `Survey` object does not exist."""
        email_list = [
            ('test@example.com', 'test@example.com', '3', 'en')
        ]

        send_emails_for_new_reports(email_list)
        self.assertEqual(email_mock.call_count, 0)

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    @mock.patch('django.template.base.Template')
    def test_email_is_sent_using_tenant_specific_templates(self, get_template_mock, email_mock):
        survey = make_survey(sid='3', tenant='ads')
        email_list = [
            ('test@example.com', 'test@example.com', survey.sid, 'en')
        ]

        send_emails_for_new_reports(email_list)

        for call in get_template_mock.call_args_list:
            template_name = call[0][0]
            self.assertIn('ads', template_name)

        survey = make_survey(sid='4', tenant='news')
        email_list = [
            ('test@example.com', 'test@example.com', survey.sid, 'en')
        ]

        send_emails_for_new_reports(email_list)
        for call in get_template_mock.call_args_list[3:]:
            template_name = call[0][0]
            self.assertIn('news', template_name)

    @mock.patch('google.appengine.api.mail.EmailMessage.send')
    @mock.patch('core.tasks.render_email_template',
                return_value=('subject', 'text vesion', '<html>html version</html>'))
    def test_email_is_sent_using_language_specific_templates(self, render_email_template_mock, email_mock):
        survey = make_survey(sid='3', tenant='news')
        email_list = [
            ('test@example.com', 'test@example.com', survey.sid, 'en')
        ]

        send_emails_for_new_reports(email_list)

        args, kwargs = render_email_template_mock.call_args
        tenant, context, lang = args
        self.assertEqual(tenant, 'news')
        self.assertEqual(lang, 'en')
        # news is not a translated tenant, we should not have localised link
        self.assertFalse('/en/' in context['url'])

        survey = make_survey(sid='4', tenant='ads')
        email_list = [
            ('test@example.com', 'test@example.com', survey.sid, 'es')
        ]

        send_emails_for_new_reports(email_list)

        args, kwargs = render_email_template_mock.call_args
        tenant, context, lang = args
        self.assertEqual(tenant, 'ads')
        self.assertEqual(lang, 'es')
        # ads is a translated tenant, we're expecting to have url localised
        self.assertTrue('/es/' in context['url'])

        survey = make_survey(sid='5', tenant='ads')
        email_list = [
            ('test@example.com', 'test@example.com', survey.sid, 'en')
        ]

        send_emails_for_new_reports(email_list)

        args, kwargs = render_email_template_mock.call_args
        tenant, context, lang = args
        self.assertEqual(tenant, 'ads')
        self.assertEqual(lang, 'en')
        # ads is a translated tenant, we're expecting to have url localised
        self.assertTrue('/en/' in context['url'])


@override_settings(
    TENANTS=MOCKED_TENANTS
)
class GenerateExportTestCase(TestCase):

    def setUp(self):
        self.tenant = 'tenant1'
        self.survey_fields = [
            'id',
            'company_name',
            'industry',
            'country',
            'created_at',
            'engagement_lead',
            'tenant',
            'excluded_from_best_practice',
            'dmb',
            'account_id'
        ]
        self.survey_result_fields = [
            'access',
            'audience',
            'attribution',
            'ads',
            'organization',
            'automation',
        ]

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    def test_generate_export_empty(self, cloud_mock, copy_mock):
        generate_csv_export(self.tenant, self.survey_fields, self.survey_result_fields, 'tenant1')
        # check mock called the write for writing headers
        header = ','.join(self.survey_fields + self.survey_result_fields) + '\n'
        handle = cloud_mock()
        handle.write.assert_called_once_with(header)

        # check a copy is made
        copy_mock.assert_called_once()

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    def test_generate_export_one_survey(self, cloud_mock, copy_mock):
        make_survey(tenant='tenant1')
        generate_csv_export(self.tenant, self.survey_fields, self.survey_result_fields, 'tenant1')
        handle = cloud_mock()

        # called once for headers and once for survey
        self.assertEqual(handle.write.call_count, 2)

        # check a copy is made
        copy_mock.assert_called_once()

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    def test_generate_export_multi_survey(self, cloud_mock, copy_mock):
        make_survey(tenant='tenant1')
        make_survey(tenant='tenant1')
        generate_csv_export(self.tenant, self.survey_fields, self.survey_result_fields, 'tenant1')
        handle = cloud_mock()

        # called once for headers and once for each survey
        self.assertEqual(handle.write.call_count, 3)

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    @override_settings(
        COUNTRIES=OrderedDict([
            ('AX', 'Åland Islands'),
        ])
    )
    def test_generate_export_survey_unicode(self, cloud_mock, copy_mock):
        make_survey(tenant='tenant1', company_name=u'ññññññññ')
        make_survey(tenant='tenant1', country='AX')  # unicode country
        generate_csv_export(self.tenant, self.survey_fields, self.survey_result_fields, 'tenant1')
        handle = cloud_mock()

        # called once for headers and once for each survey
        self.assertEqual(handle.write.call_count, 3)
        # check a copy is made
        copy_mock.assert_called_once()

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    def test_generate_export_multi_survey_with_results(self, cloud_mock, copy_mock):
        survey_1 = make_survey(tenant='tenant1')
        survey_res = make_survey_result(survey=survey_1)
        survey_1.last_survey_result = survey_res
        survey_1.save()

        survey_2 = make_survey(tenant='tenant1')
        survey_res = make_survey_result(survey=survey_2)
        survey_2.last_survey_result = survey_res
        survey_2.save()

        generate_csv_export(self.tenant, self.survey_fields, self.survey_result_fields, 'tenant1')
        handle = cloud_mock()

        # called once for headers and once for each survey
        self.assertEqual(handle.write.call_count, 3)

    @mock.patch('cloudstorage.copy2')
    @mock.patch('cloudstorage.open', new_callable=mock.mock_open)
    def test_generate_export_multi_survey_multi_tenant(self, cloud_mock, copy_mock):
        make_survey(tenant='tenant1')
        make_survey(tenant='tenant2')
        make_survey(tenant='tenant2')
        handle = cloud_mock()

        generate_csv_export('tenant1', self.survey_fields, self.survey_result_fields, 'tenant1')

        # called once for headers and once for each survey
        self.assertEqual(handle.write.call_count, 2)

        # reset the mock to calculate rows for tenant2
        cloud_mock().reset_mock()
        generate_csv_export('tenant2', self.survey_fields, self.survey_result_fields, 'tenant2')

        # called once for headers and once for each survey
        self.assertEqual(handle.write.call_count, 3)


class UpdateResponsesWithTextTestCase(TestCase):
    """Tests for _update_responses_with_text function."""

    def test_update_responses_with_text_values_and_text_match(self):
        """When values and text match, all items are merged in the result."""

        responses_values = get_mocked_results().get('responses')
        responses_text = get_mocked_results(text=True).get('responses')

        responses_values_ids = [response.get('ResponseID') for response in responses_values
                                if response.get('Finished') == '1']

        responses_text_ids = [response.get('ResponseID') for response in responses_text
                              if response.get('Finished') == '1']

        responses = _update_responses_with_text(responses_values, responses_text)

        self.assertEqual(len(responses), len(responses_values))
        for val in responses_values_ids:
            self.assertIn(val, responses.keys())

        self.assertEqual(len(responses), len(responses_text))

        for val in responses_text_ids:
            self.assertIn(val, responses)

    def test_update_responses_with_text_more_values_than_text(self):
        """When values has more items than text, result is updated were possible."""

        responses_values = get_mocked_results().get('responses')
        responses_text = get_mocked_results(text=True).get('responses')

        responses_values.append({
            'Organization-sum': '0.0',
            'Organization-weightedAvg': '0.0',
            'Organization-weightedStdDev': '0.0',
            'sid': '1',
            'ResponseID': 'BBB',
            'Enter Embedded Data Field Name Here...': '',
            'sponsor': '',
            'company_name': 'new survey',
            'dmb': '0.5',
            'StartDate': '2018-07-31 14:16:06',
            'EndDate': '2018-07-31 15:18:56',
            'Q1_1_TEXT': '',
            'Q1_2_TEXT': '',
            'Q2_1_TEXT': '',
            'Q2_2_TEXT': '',

            'Q3': '2',
            'Q4': '0',
            'Q5_1': '2',

            'Q5_2': '0',
            'Q5_3': '3',
            'Q6': '4',
            'Q7': '2',

            'Q8': '4',
            'Q10': '0',
            'Q11': '1',
            'Q12': '2',
            'Finished': '1',
        })

        responses_values_ids = [response.get('ResponseID') for response in responses_values
                                if response.get('Finished') == '1']

        responses_text_ids = [response.get('ResponseID') for response in responses_text
                              if response.get('Finished') == '1']

        responses = _update_responses_with_text(responses_values, responses_text)

        self.assertEqual(len(responses), len(responses_values))
        for val in responses_values_ids:
            self.assertIn(val, responses.keys())

        self.assertNotIn('BBB', responses_text_ids)

    def test_update_responses_with_text_more_text_than_values(self):
        """When text has more items than values, text elements not in values should be skipped."""

        responses_values = get_mocked_results().get('responses')
        responses_text = get_mocked_results(text=True).get('responses')

        responses_text.append({
            'Organization-sum': '0.0',
            'Organization-weightedAvg': '0.0',
            'Organization-weightedStdDev': '0.0',
            'sid': '1',
            'ResponseID': 'BBB',
            'Enter Embedded Data Field Name Here...': '',
            'sponsor': '',
            'company_name': 'new survey',
            'dmb': '0.5',
            'StartDate': '2018-07-31 14:16:06',
            'EndDate': '2018-07-31 15:18:56',
            'Q1_1_TEXT': '',
            'Q1_2_TEXT': '',
            'Q2_1_TEXT': '',
            'Q2_2_TEXT': '',

            'Q3': 'Some text for answer Q3',
            'Q4': 'Some text for answer Q4',
            'Q5_1': 'Some text for answer Q5_1',
            'Q5_2': 'Some text for answer Q5_2',
            'Q5_3': 'Some text for answer Q5_3',
            'Q6': 'Some text for answer Q6',
            'Q7': 'Some text for answer Q7',
            'Q8': 'Some text for answer Q8',
            'Q10': 'Some text for answer Q10',
            'Q11': 'Some text for answer Q11',
            'Q12': 'Some text for answer Q12',
            'Finished': '1',
        })

        responses_values_ids = [response.get('ResponseID') for response in responses_values
                                if response.get('Finished') == '1']

        responses = _update_responses_with_text(responses_values, responses_text)

        self.assertEqual(len(responses), len(responses_values))
        for val in responses_values_ids:
            self.assertIn(val, responses.keys())

        self.assertNotIn('BBB', responses.keys())
        self.assertNotIn('BBB', responses_values_ids)


@override_settings(
    TENANTS=MOCKED_TENANTS,
)
class GetDefinitionTestCase(TestCase):
    """Tests for _get_definition function"""

    def setUp(self):
        self.survey_id = 'surveyid'
        self.tenant = 'tenant1'

    @mock.patch('core.qualtrics.download.fetch_survey', return_value=get_survey_definition())
    def test_new_definition_firts_time(self, download_mock):
        """When there are not survey definition, the first downloaded needs to be stored."""
        self.assertEqual(SurveyDefinition.objects.count(), 0)
        last_definition = _get_definition(self.tenant, self.survey_id)
        self.assertEqual(SurveyDefinition.objects.count(), 1)
        last_stored = SurveyDefinition.objects.latest('last_modified')
        self.assertIsNotNone(last_definition)
        self.assertEqual(last_definition.pk, last_stored.pk)

    @mock.patch('core.qualtrics.download.fetch_survey', return_value=get_survey_definition())
    def test_new_definition_found(self, download_mock):
        """
        When the new downloaded survey definition last modified date is grater than the last stored one,
        it should be saved.
        """

        # create a survey definition way in the past respect to the mock we have
        make_survey_definition(tenant='tenant1', last_modified=dateparse.parse_datetime('2015-11-29T13:27:15Z'))
        self.assertEqual(SurveyDefinition.objects.count(), 1)
        last_definition = _get_definition(self.tenant, self.survey_id)
        # a new definition should be downloaded
        self.assertEqual(SurveyDefinition.objects.count(), 2)
        last_stored = SurveyDefinition.objects.latest('last_modified')
        self.assertIsNotNone(last_definition)
        self.assertEqual(last_definition.pk, last_stored.pk)

    @mock.patch('core.qualtrics.download.fetch_survey', return_value=get_survey_definition())
    def test_new_definition_dont_need_update(self, download_mock):
        """
        When the new downloaded survey definition last modified date is not grater than the last stored one,
        it should not be saved.
        """
        make_survey_definition(tenant='tenant1', last_modified=dateparse.parse_datetime('2019-01-28T16:04:23Z'))
        self.assertEqual(SurveyDefinition.objects.count(), 1)
        last_definition = _get_definition(self.tenant, self.survey_id)
        # a new definition should not be downloaded
        self.assertEqual(SurveyDefinition.objects.count(), 1)
        last_stored = SurveyDefinition.objects.latest('last_modified')
        self.assertIsNotNone(last_definition)
        self.assertEqual(last_definition.pk, last_stored.pk)

    @mock.patch('core.qualtrics.download.fetch_survey')
    def test_definition_download_fails(self, download_mock):
        exception_body = {
            'meta': {
                'httpStatus': 400,
                'error': {
                    'errorMesasge': 'some error'
                }
            }
        }
        download_mock.side_effect = FetchResultException(exception_body)
        with mock.patch('logging.error') as logging_mock:
            last_definition = _get_definition(self.tenant, self.survey_id)
            self.assertIsNone(last_definition)
            self.assertTrue(logging_mock.called)

    @mock.patch('core.qualtrics.download.fetch_survey', return_value=get_survey_definition())
    def test_fetch_survey_called_with_right_parameters(self, download_mock):
        """When fetch_survey is called, check is called with right paramenters."""
        _get_definition(self.tenant, self.survey_id)

        self.assertTrue(download_mock.called)
        self.assertEqual(download_mock.call_count, 1)
        all_calls = download_mock.call_args_list

        args, kwargs = all_calls[0]
        self.assertEqual(len(args), 1)
        self.assertIsNotNone(args[0])

    @mock.patch('core.qualtrics.download.fetch_survey', return_value=get_survey_definition())
    def test_new_definition_found_multi_tenant(self, download_mock):
        """
        When the new downloaded survey definition last modified date is grater than the last stored one,
        it should be saved.
        """

        # create a survey definition way in the past respect to the mock we have
        make_survey_definition(tenant='tenant1', last_modified=dateparse.parse_datetime('2015-11-29T13:27:15Z'))
        make_survey_definition(tenant='tenant2', last_modified=dateparse.parse_datetime('2015-11-29T13:27:15Z'))
        self.assertEqual(SurveyDefinition.objects.count(), 2)
        last_definition = _get_definition(self.tenant, self.survey_id)
        # a new definition should be downloaded for tenant 1
        self.assertEqual(SurveyDefinition.objects.count(), 3)
        self.assertEqual(SurveyDefinition.objects.filter(tenant='tenant1').count(), 2)
        self.assertEqual(SurveyDefinition.objects.filter(tenant='tenant2').count(), 1)

        last_stored = SurveyDefinition.objects.filter(tenant='tenant1').latest('last_modified')
        self.assertIsNotNone(last_definition)
        self.assertEqual(last_definition.pk, last_stored.pk)
        self.assertEqual(last_definition.last_modified, dateparse.parse_datetime('2018-12-11T17:22:31Z'))


@override_settings(
    TENANTS=MOCKED_TENANTS,
    MIN_ITEMS_INDUSTRY_THRESHOLD=2,
    MIN_ITEMS_BEST_PRACTICE_THRESHOLD=2,
)
class CalculateIndustryBenchmark(TestCase):
    """Tests for calculate_industry_benchmark function"""

    def setUp(self):
        self.survey_id = 'surveyid'

    def test_no_initial_values(self):
        """When there are no IndustryBencmark objects, after calculate benchmark
        run, we should have all the industries from ic-o to root saved as
        IndustryBenchmark."""
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 0)

        make_survey_with_result(industry='ic-o', tenant='tenant1')
        calculate_industry_benchmark('tenant1')

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 3)

    def test_has_initial_values(self):
        """When there are IndustryBencmark objects, after calculate benchmark
        run, we should have all the industries from ic-o to root saved as
        IndustryBenchmark, with values updated."""
        IndustryBenchmark.objects.create(
            industry='ic-o',
            tenant='tenant1',
            initial_dmb=1.0,
            initial_dmb_d={},
            initial_best_practice=2.0,
            initial_best_practice_d={},
            sample_size=10
        )
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 1)
        make_survey_with_result(industry='ic-o', tenant='tenant1')
        calculate_industry_benchmark('tenant1')

        # check all industries `all -- ic -- ic-o` are present
        self.assertEqual(len(IndustryBenchmark.objects.all()), 3)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='ic-o')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='ic')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='all')), 1)

    def test_no_surveys_should_not_update_benchmarks(self):
        """When there are IndustryBencmark objects, but there are no survey results,
        calculation should be left untouched."""
        IndustryBenchmark.objects.create(
            industry='ic-o',
            tenant='tenant1',
            initial_dmb=1.0,
            initial_dmb_d={},
            initial_best_practice=2.0,
            initial_best_practice_d={},
            sample_size=10
        )

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.all()), 1)

        calculate_industry_benchmark('tenant1')

        self.assertEqual(len(IndustryBenchmark.objects.all()), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 1)

    def test_multi_tenant(self):
        """IndustryBencmark objects are handled tenant based."""
        IndustryBenchmark.objects.create(
            industry='ic-o',
            tenant='tenant1',
            initial_dmb=1.0,
            initial_dmb_d={},
            initial_best_practice=2.0,
            initial_best_practice_d={},
            sample_size=10
        )
        IndustryBenchmark.objects.create(
            industry='edu-o',
            tenant='tenant2',
            initial_dmb=1.0,
            initial_dmb_d={},
            initial_best_practice=2.0,
            initial_best_practice_d={},
            sample_size=10
        )
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant2')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.all()), 2)

        # create a survey for tenant1
        make_survey_with_result(industry='ic-o', tenant='tenant1')
        calculate_industry_benchmark('tenant1')

        # check all industries `all -- ic -- ic-o` are present
        self.assertEqual(len(IndustryBenchmark.objects.all()), 4)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='ic-o')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='ic')), 1)
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1', industry='all')), 1)
        # but the one for tenant2 should be left untouched
        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant2')), 1)

    def test_excluded_dimension_should_not_count(self):
        """When there are IndustryBencmark objects, if a dimension is
        excluded, it should not be considered in calculation."""

        dmb_d_res_1 = {
            'attribution': 4.0,
            'ads': 2.0,
            'automation': None,
        }

        dmb_d_res_2 = {
            'attribution': 6.0,
            'ads': None,
            'automation': 1.0,
        }

        IndustryBenchmark.objects.create(
            industry='ic-o',
            tenant='tenant1',
            initial_dmb=0.0,
            initial_dmb_d={},
            initial_best_practice=0.0,
            initial_best_practice_d={},
            sample_size=10
        )

        survey_1 = make_survey(industry='ic-o', tenant='tenant1')
        survey_2 = make_survey(industry='ic-o', tenant='tenant1')

        survey_res_1 = make_survey_result(survey=survey_1, dmb_d=dmb_d_res_1)
        survey_1.last_survey_result = survey_res_1
        survey_1.save()

        survey_res_2 = make_survey_result(survey=survey_2, dmb_d=dmb_d_res_2)
        survey_2.last_survey_result = survey_res_2
        survey_2.save()

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 1)
        self.assertEqual(len(Survey.objects.filter(tenant='tenant1')), 2)
        self.assertEqual(len(IndustryBenchmark.objects.all()), 1)

        calculate_industry_benchmark('tenant1')

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant1')), 3)

        ib = IndustryBenchmark.objects.get(tenant='tenant1', industry='ic-o')

        self.assertAlmostEqual(float(ib.dmb_value), 2.67, places=2)
        self.assertEqual(ib.dmb_d_value.get('attribution'), 5.0)
        self.assertEqual(ib.dmb_d_value.get('ads'), 2.0)
        self.assertEqual(ib.dmb_d_value.get('automation'), 1.0)

    @override_settings(
        TENANTS=MOCKED_TENANTS,
        MIN_ITEMS_INDUSTRY_THRESHOLD=2,
        MIN_ITEMS_BEST_PRACTICE_THRESHOLD=2,
        NEWS='tenant2',
    )
    def test_excluded_dimension_should_not_count_tenant_2(self):
        """When there are IndustryBencmark objects, if a dimension is
        excluded, it should not be considered in calculation."""

        initial_dmb_d = {
            'attribution': 2.0,
            'ads': None,
            'automation': 3.0,
        }

        initial_dmb_d_bp = {
            'attribution': 3.5,
            'ads': 1.5,
            'automation': 4.0,
        }

        dmb_d_res_1 = {
            'attribution': 4.0,
            'ads': 2.0,
            'automation': None,
        }

        dmb_d_res_2 = {
            'attribution': 6.0,
            'ads': None,
            'automation': 1.0,
        }

        IndustryBenchmark.objects.create(
            industry='ic-bnpj',
            tenant='tenant2',
            initial_dmb=2.5,
            initial_dmb_d=initial_dmb_d,
            initial_best_practice=3.9,
            initial_best_practice_d=initial_dmb_d_bp,
            dmb_value=2.5,
            dmb_d_value=initial_dmb_d,
            dmb_bp_value=3.9,
            dmb_d_bp_value=initial_dmb_d_bp,
            sample_size=10
        )

        survey_1 = make_survey(industry='ic-bnpj', tenant='tenant2')
        survey_2 = make_survey(industry='ic-bnpj', tenant='tenant2')

        survey_res_1 = make_survey_result(survey=survey_1, dmb_d=dmb_d_res_1, dmb=2.0)
        survey_1.last_survey_result = survey_res_1
        survey_1.save()

        survey_res_2 = make_survey_result(survey=survey_2, dmb_d=dmb_d_res_2, dmb=4.0)
        survey_2.last_survey_result = survey_res_2
        survey_2.save()

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant2')), 1)
        self.assertEqual(len(Survey.objects.filter(tenant='tenant2')), 2)
        self.assertEqual(len(IndustryBenchmark.objects.all()), 1)

        calculate_industry_benchmark('tenant2')

        self.assertEqual(len(IndustryBenchmark.objects.filter(tenant='tenant2')), 1)

        ib = IndustryBenchmark.objects.get(tenant='tenant2', industry='ic-bnpj')

        # check that values are unchanged, and only initial values are kept
        self.assertEqual(ib.dmb_d_value.get('attribution'), 2.0)
        self.assertEqual(ib.dmb_d_value.get('ads'), None)
        self.assertEqual(ib.dmb_d_value.get('automation'), 3.0)
        # average of survey result dmb
        self.assertAlmostEqual(float(ib.dmb_value), 2.5, places=2)
        # max of survey result dmb
        self.assertAlmostEqual(float(ib.dmb_bp_value), 3.9, places=2)


class RenderEmailTemplateTestCase(TestCase):

    @mock.patch('django.utils.translation.activate')
    # @mock.patch('core.tasks.get_template')
    @mock.patch('django.template.base.Template')
    def test_render_email_template_english_language(self, get_template_mock, translation_mock):
        # get_template_mock().render = mock.MagicMock(return_value=['some random subject'])

        survey = make_survey(sid='3', tenant='ads')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        render_email_template(survey.tenant, context, 'en')

        for call in get_template_mock.call_args_list:
            template_name = call[0][0]
            self.assertIn('ads', template_name)

        all_calls = translation_mock.call_args_list

        first_call_args, _ = all_calls[0]
        second_call_args, _ = all_calls[1]

        self.assertEqual(first_call_args[0], 'en')
        self.assertEqual(second_call_args[0], 'en')

    @mock.patch('django.utils.translation.activate')
    @mock.patch('django.template.base.Template')
    def test_render_email_template_other_language(self, get_template_mock, translation_mock):
        """When the template is rendered in another language, it's ativated first,
        and later the english (default) is activated back again."""
        # get_template_mock.render = mock.MagicMock(return_value=['some random subject'])

        survey = make_survey(sid='3', tenant='ads')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        render_email_template(survey.tenant, context, 'es')

        for call in get_template_mock.call_args_list:
            template_name = call[0][0]
            self.assertIn('ads', template_name)

        all_calls = translation_mock.call_args_list

        first_call_args, _ = all_calls[0]
        second_call_args, _ = all_calls[1]

        self.assertEqual(first_call_args[0], 'es')
        self.assertEqual(second_call_args[0], 'en')

    @mock.patch('django.template.base.Template')
    def test_render_email_template_english_rendered(self, get_template_mock):
        """When the template is rendered in another language, it's ativated first,
        and later the english (default) is activated back again."""
        get_template_mock.render = mock.MagicMock(return_value=['some random subject'])
        survey = make_survey(sid='3', tenant='ads')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }
        subject, text, html = render_email_template(survey.tenant, context, 'es')

        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)

    def test_render_email_template_not_existent_lanaguage_rendered(self):
        """When the template is rendered in another language, it's ativated first,
        and later the english (default) is activated back again."""
        survey = make_survey(sid='3', tenant='ads')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        subject, text, html = render_email_template(survey.tenant, context, 'wrong')
        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)


class RenderEmailTemplateIntegration(TestCase):

    @unittest.skipIf(settings.TENANTS.get(settings.ADS) is None, "Advertisers tenant is excluded")
    def test_render_email_template_ads(self):
        """Test if template files are rendered correctly for ads tenant"""
        survey = make_survey(sid='3', tenant='ads')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        tenant = survey.tenant
        ads_html_message_template = get_template("public/{}/email/response_ready_email_body.html".format(tenant))
        ads_text_message_template = get_template("public/{}/email/response_ready_email_body.txt".format(tenant))
        text_message_rendered = ads_text_message_template.render(context)
        html_message_rendered = ads_html_message_template.render(context)

        subject, text, html = render_email_template(survey.tenant, context, 'en')
        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)
        self.assertEqual(subject, "Response is ready!")
        self.assertEqual(text, text_message_rendered)
        self.assertEqual(html, html_message_rendered)

    @unittest.skipIf(settings.TENANTS.get(settings.NEWS) is None, "News tenant is excluded")
    def test_render_email_template_news(self):
        """Test if template files are rendered correctly for news tenant"""
        survey = make_survey(sid='3', tenant='news')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        tenant = survey.tenant

        # load email content templates from file
        ads_html_message_template = get_template("public/{}/email/response_ready_email_body.html".format(tenant))
        ads_text_message_template = get_template("public/{}/email/response_ready_email_body.txt".format(tenant))
        text_message_rendered = ads_text_message_template.render(context)
        html_message_rendered = ads_html_message_template.render(context)

        subject, text, html = render_email_template(survey.tenant, context, 'en')
        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)
        self.assertEqual(subject, "Response is ready!")
        self.assertEqual(text, text_message_rendered)
        self.assertEqual(html, html_message_rendered)

    @unittest.skipIf(settings.TENANTS.get(settings.RETAIL) is None, "Retail tenant is excluded")
    def test_render_email_template_retail(self):
        """Test if template files are rendered correctly for retail tenant"""
        survey = make_survey(sid='3', tenant='retail')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        tenant = survey.tenant
        ads_html_message_template = get_template("public/{}/email/response_ready_email_body.html".format(tenant))
        ads_text_message_template = get_template("public/{}/email/response_ready_email_body.txt".format(tenant))
        text_message_rendered = ads_text_message_template.render(context)
        html_message_rendered = ads_html_message_template.render(context)

        subject, text, html = render_email_template(survey.tenant, context, 'en')
        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)
        self.assertEqual(subject, "Response is ready!")
        self.assertEqual(text, text_message_rendered)
        self.assertEqual(html, html_message_rendered)

    @unittest.skipIf(settings.TENANTS.get(settings.CLOUD) is None, "Cloud tenant is excluded")
    def test_render_email_template_cloud(self):
        """Test if template files are rendered correctly for cloud tenant"""
        survey = make_survey(sid='3', tenant='cloud')

        context = {
            'url': "http://{}{}".format('domain', 'link'),
            'company_name': survey.company_name,
            'industry': survey.industry,
            'country': survey.country,
        }

        tenant = survey.tenant
        ads_html_message_template = get_template("public/{}/email/response_ready_email_body.html".format(tenant))
        ads_text_message_template = get_template("public/{}/email/response_ready_email_body.txt".format(tenant))
        text_message_rendered = ads_text_message_template.render(context)
        html_message_rendered = ads_html_message_template.render(context)

        subject, text, html = render_email_template(survey.tenant, context, 'en')
        self.assertIsNotNone(subject)
        self.assertIsNotNone(text)
        self.assertIsNotNone(html)
        self.assertEqual(subject, "{}: Google Cloud Maturity Assessment Report".format(survey.company_name))
        self.assertEqual(text, text_message_rendered)
        self.assertEqual(html, html_message_rendered)


class ExportTenantDataSuperAdmin(TestCase):
    """Tests for export_tenant_data function, when is_super_admin is `True`"""

    def setUp(self):
        self.share_with = "share_with@email.com"
        self.is_super_admin = True
        # engagement lead doesn't really matter when superadmin, since all the data will be exported
        self.engagement_lead = "1233454567"
        make_user(email=self.share_with, is_superuser=self.is_super_admin)

    @override_settings(
        TENANTS=MOCKED_TENANTS,
    )
    @mock.patch('core.googleapi.sheets.export_data')
    def test_all_surveys_no_results(self, mocked_export):
        """When there are no SurveyResults, the underlying function is still called with the correct data"""
        make_survey(tenant='tenant1')
        make_survey(tenant='tenant1')

        survey_fields_mappings = {
            'company_name': 'Company Name',
            'country': 'Country',
            'industry': 'Industry',
            'created_at': 'Creation Date',
            'link': 'Report link',
        }

        survey_result_fields_mapping = {
            'dmb': 'Overall DMB',
            'excluded_from_best_practice': 'Excluded from Benchmark',
            'access': 'Access',
            'audience': 'Audience',
            'attribution': 'Attribution',
            'ads': 'Ads',
            'organization': 'Organization',
            'automation': 'Automation',
        }
        title = "A meaningful title"

        export_tenant_data(
            title,
            'tenant1',
            self.is_super_admin,
            self.engagement_lead,
            survey_fields_mappings,
            survey_result_fields_mapping,
            self.share_with,
        )
        expected_headers = survey_fields_mappings.values() + survey_result_fields_mapping.values()
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual(title, got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

    @override_settings(
        TENANTS=MOCKED_TENANTS,
    )
    @mock.patch('core.googleapi.sheets.export_data')
    def test_survey_results(self, mocked_export):
        """When there are no SurveyResults, the underlying function is still called with the correct data"""
        make_survey_with_result(industry='ic-bnpj', tenant='tenant2')
        make_survey_with_result(industry='ic-bnpj', tenant='tenant2')
        make_survey_with_result(industry='ic-bnpj', tenant='tenant2')

        survey_fields_mappings = {
            'company_name': 'Company Name',
            'country': 'Country',
            'industry': 'Industry',
            'created_at': 'Creation Date',
            'link': 'Report link',
        }

        survey_result_fields_mapping = {
            'dmb': 'Overall DMB',
            'excluded_from_best_practice': 'Excluded from Benchmark',
            'access': 'Access',
            'audience': 'Audience',
            'attribution': 'Attribution',
            'ads': 'Ads',
            'organization': 'Organization',
            'automation': 'Automation',
        }
        title = "A meaningful title"

        export_tenant_data(
            title,
            'tenant2',
            self.is_super_admin,
            self.engagement_lead,
            survey_fields_mappings,
            survey_result_fields_mapping,
            self.share_with,
        )
        expected_headers = survey_fields_mappings.values() + survey_result_fields_mapping.values()
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 3 items
        self.assertEqual(title, got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 3)

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_ads_tenant(self, mocked_export):
        """When tenant is advertisers, it's exported with the correct configured keys."""
        tenant = 'ads'
        s1 = make_survey_with_result(industry='ic-bnpj', tenant=tenant)
        s2 = make_survey_with_result(industry='ic-bnpj', tenant=tenant)

        s1.last_survey_result.dmb_d = {
            'access': 1.5,
            'audience': 1.3,
            'attribution': 1.6,
            'ads': 1.5,
            'organization': 2.0,
            'automation': 3.0,
        }
        s1.save()

        s2.last_survey_result.dmb_d = {
            'access': 2.5,
            'audience': 2.3,
            'attribution': 2.6,
            'ads': 2.5,
            'organization': 4.0,
            'automation': 3.0,
        }
        s2.save()

        tenant_conf = settings.TENANTS[tenant]
        ads_title = "Ads Export"

        export_tenant_data(
            ads_title,
            tenant,
            self.is_super_admin,
            self.engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )
        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 3 items
        self.assertEqual("Ads Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_news_tenant(self, mocked_export):
        """When tenant is publishers, it's exported with the correct configured keys."""
        tenant = 'news'
        make_survey_with_result(industry='ic-bnpj', tenant=tenant)
        make_survey_with_result(industry='ic-bnpj', tenant=tenant)

        tenant_conf = settings.TENANTS[tenant]
        news_title = "News Export"

        export_tenant_data(
            news_title,
            tenant,
            self.is_super_admin,
            self.engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )
        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 3 items
        self.assertEqual("News Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_retail_tenant(self, mocked_export):
        """When tenant is retail, it's exported with the correct configured keys."""
        tenant = 'retail'
        make_survey_with_result(industry='rt-o', tenant=tenant)
        make_survey_with_result(industry='rt-o', tenant=tenant)

        tenant_conf = settings.TENANTS[tenant]
        retail_title = "Retail Export"

        export_tenant_data(
            retail_title,
            tenant,
            self.is_super_admin,
            self.engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )
        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual("Retail Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))


class ExportTenantDataNotSuperAdmin(TestCase):
    """Tests for export_tenant_data function, when is_super_admin is `False`"""

    def setUp(self):
        self.share_with = "share_with@email.com"
        self.is_super_admin = False
        self.user = make_user(email=self.share_with, is_superuser=self.is_super_admin)

    @override_settings(
        TENANTS=MOCKED_TENANTS,
    )
    @mock.patch('core.googleapi.sheets.export_data')
    def test_all_surveys_no_results(self, mocked_export):
        """When there are no SurveyResults, the underlying function is still called with the correct data"""
        engagement_lead = '12345'
        s1 = make_survey(tenant='tenant1', engagement_lead=engagement_lead, creator=self.user)
        s2 = make_survey(tenant='tenant1', engagement_lead=engagement_lead, creator=self.user)
        make_survey(tenant='tenant1', engagement_lead='67891')

        self.user.accounts.add(s1)
        self.user.accounts.add(s2)
        self.user.save()

        survey_fields_mappings = {
            'company_name': 'Company Name',
            'country': 'Country',
            'industry': 'Industry',
            'created_at': 'Creation Date',
            'link': 'Report link',
        }

        survey_result_fields_mapping = {
            'dmb': 'Overall DMB',
            'excluded_from_best_practice': 'Excluded from Benchmark',
            'access': 'Access',
            'audience': 'Audience',
            'attribution': 'Attribution',
            'ads': 'Ads',
            'organization': 'Organization',
            'automation': 'Automation',
        }
        title = "A meaningful title"
        export_tenant_data(
            title,
            'tenant1',
            self.is_super_admin,
            engagement_lead,
            survey_fields_mappings,
            survey_result_fields_mapping,
            self.share_with,
        )
        expected_headers = survey_fields_mappings.values() + survey_result_fields_mapping.values()
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual(title, got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

    @override_settings(
        TENANTS=MOCKED_TENANTS,
    )
    @mock.patch('core.googleapi.sheets.export_data')
    def test_survey_results(self, mocked_export):
        """When there are no SurveyResults, the underlying function is still called with the correct data"""
        engagement_lead = '12345'
        s1 = make_survey_with_result(
            industry='ic-bnpj',
            tenant='tenant2',
            engagement_lead=engagement_lead,
            creator=self.user
        )
        s2 = make_survey_with_result(
            industry='ic-bnpj',
            tenant='tenant2',
            engagement_lead=engagement_lead,
            creator=self.user
        )
        s3 = make_survey_with_result(
            industry='ic-bnpj',
            tenant='tenant2',
            engagement_lead=engagement_lead,
            creator=self.user
        )
        make_survey_with_result(industry='ic-bnpj', tenant='tenant2', engagement_lead='6789')
        make_survey_with_result(industry='ic-bnpj', tenant='tenant2', engagement_lead='6789')

        self.user.accounts.add(s1)
        self.user.accounts.add(s2)
        self.user.accounts.add(s3)
        self.user.save()

        survey_fields_mappings = {
            'company_name': 'Company Name',
            'country': 'Country',
            'industry': 'Industry',
            'created_at': 'Creation Date',
            'link': 'Report link',
        }

        survey_result_fields_mapping = {
            'dmb': 'Overall DMB',
            'excluded_from_best_practice': 'Excluded from Benchmark',
            'access': 'Access',
            'audience': 'Audience',
            'attribution': 'Attribution',
            'ads': 'Ads',
            'organization': 'Organization',
            'automation': 'Automation',
        }
        title = "A meaningful title"

        export_tenant_data(
            title,
            'tenant2',
            self.is_super_admin,
            engagement_lead,
            survey_fields_mappings,
            survey_result_fields_mapping,
            self.share_with,
        )
        expected_headers = survey_fields_mappings.values() + survey_result_fields_mapping.values()
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 3 items
        self.assertEqual(title, got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 3)

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_ads_tenant(self, mocked_export):
        """When tenant is advertisers, it's exported with the correct configured keys."""
        tenant = 'ads'
        engagement_lead = '12345'
        s1 = make_survey_with_result(
            industry='ic-bnpj',
            tenant=tenant,
            engagement_lead=engagement_lead,
            creator=self.user
        )
        s2 = make_survey_with_result(
            industry='ic-bnpj',
            tenant=tenant,
            engagement_lead=engagement_lead,
            creator=self.user
        )
        s3 = make_survey_with_result(industry='ic-bnpj', tenant=tenant, engagement_lead="6789")

        self.user.accounts.add(s1)
        self.user.accounts.add(s2)
        self.user.save()

        s1.last_survey_result.dmb_d = {
            'access': 1.5,
            'audience': 1.3,
            'attribution': 1.6,
            'ads': 1.5,
            'organization': 2.0,
            'automation': 3.0,
        }
        s1.save()

        s2.last_survey_result.dmb_d = {
            'access': 2.5,
            'audience': 2.3,
            'attribution': 2.6,
            'ads': 2.5,
            'organization': 4.0,
            'automation': 3.0,
        }
        s2.save()

        s3.last_survey_result.dmb_d = {
            'access': 2.5,
            'audience': 2.3,
            'attribution': 2.6,
            'ads': 2.5,
            'organization': 4.0,
            'automation': 3.0,
        }
        s3.save()

        tenant_conf = settings.TENANTS[tenant]
        ads_title = "Ads Export"

        export_tenant_data(
            ads_title,
            tenant,
            self.is_super_admin,
            engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )
        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual("Ads Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        # make sure only the requested engagement lead is exported
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_news_tenant(self, mocked_export):
        """When tenant is publishers, it's exported with the correct configured keys."""
        tenant = 'news'
        engagement_lead = '11111'
        s1 = make_survey_with_result(
            industry='ic-bnpj',
            tenant=tenant,
            engagement_lead=engagement_lead,
            creator=self.user
        )
        s2 = make_survey_with_result(
            industry='ic-bnpj',
            tenant=tenant,
            engagement_lead=engagement_lead,
            creator=self.user
        )
        make_survey_with_result(industry='ic-bnpj', tenant=tenant, engagement_lead='222222')

        self.user.accounts.add(s1)
        self.user.accounts.add(s2)
        self.user.save()

        tenant_conf = settings.TENANTS[tenant]
        news_title = "News Export"

        export_tenant_data(
            news_title,
            tenant,
            self.is_super_admin,
            engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )

        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual("News Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))

    @mock.patch('core.googleapi.sheets.export_data')
    def test_export_retail_tenant(self, mocked_export):
        """When tenant is retail, it's exported with the correct configured keys."""
        tenant = 'retail'
        engagement_lead = '111111'
        s1 = make_survey_with_result(industry='rt-o', tenant=tenant, engagement_lead=engagement_lead, creator=self.user)
        s2 = make_survey_with_result(industry='rt-o', tenant=tenant, engagement_lead=engagement_lead, creator=self.user)
        make_survey_with_result(industry='rt-o', tenant=tenant, engagement_lead='3333333')

        self.user.accounts.add(s1)
        self.user.accounts.add(s2)
        self.user.save()

        tenant_conf = settings.TENANTS[tenant]
        retail_title = "Retail Export"

        export_tenant_data(
            retail_title,
            tenant,
            self.is_super_admin,
            engagement_lead,
            tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'],
            tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'],
            self.share_with,
        )

        expected_headers = tenant_conf['GOOGLE_SHEET_EXPORT_SURVEY_FIELDS'].values() + tenant_conf['GOOGLE_SHEET_EXPORT_RESULT_FIELDS'].values()  # noqa
        args, kwargs = mocked_export.call_args
        got_title, got_headers, got_rows, got_share_with = args

        # check that is has been called with 2 items
        self.assertEqual("Retail Export", got_title)
        self.assertItemsEqual(got_headers, expected_headers)
        self.assertEqual(len(got_rows), 2)

        for dim in tenant_conf['CONTENT_DATA']['dimension_titles'].values():
            self.assertTrue(dim in got_headers, "{} error".format(dim))

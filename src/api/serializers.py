from core.models import Survey, SurveyResult
from rest_framework.serializers import ModelSerializer, CharField, JSONField, ValidationError
from django.conf import settings


class SurveySerializer(ModelSerializer):

    class Meta:
        model = Survey
        fields = (
            'account_id',
            'company_name',
            'link',
            'link_sponsor',
            'engagement_lead',
            'industry',
            'country',
            'tenant',
            'slug',
        )

    def validate(self, data):
        """
        Check that an industry belongs to valid tenant's industry list.
        """
        tenant_conf = settings.TENANTS.get(data.get('tenant'))
        if tenant_conf:
            industries = tenant_conf['INDUSTRIES']
            if data['industry'] not in industries:
                raise ValidationError("Industry does not belong to a set of valid industrues for this tenant")
        return data


class SurveyAccountIdSerializer(ModelSerializer):

    class Meta:
        model = Survey
        fields = (
            'account_id',
        )


class SurveyCompanyNameSerializer(ModelSerializer):
    class Meta:
        model = Survey
        fields = ('company_name',)


class SurveyResultSerializer(ModelSerializer):
    dmb_d = JSONField()

    class Meta:
        model = SurveyResult
        fields = ('response_id', 'dmb', 'dmb_d', 'started_at')


class SurveyWithResultSerializer(ModelSerializer):
    survey_result = SurveyResultSerializer(read_only=True)
    country_name = CharField(source='get_country_display')
    industry_name = CharField(source='get_industry_display')

    class Meta:
        model = Survey
        fields = (
            'company_name',
            'industry',
            'industry_name',
            'country_name',
            'survey_result',
            'created_at',
            'tenant',
        )


class AdminSurveyResultSerializer(ModelSerializer):

    class Meta:
        model = SurveyResult
        fields = ('response_id', 'detail_link', 'report_link', 'started_at')


class AdminSurveyResultsSerializer(ModelSerializer):
    last_survey_result = SurveyResultSerializer(read_only=True)
    last_internal_result = SurveyResultSerializer(read_only=True)
    country_name = CharField(source='get_country_display')
    industry_name = CharField(source='get_parent_industry_display')

    class Meta:
        model = Survey
        fields = (
            'account_id',
            'company_name',
            'industry_name',
            'country_name',
            'last_survey_result',
            'last_internal_result',
            'created_at',
        )

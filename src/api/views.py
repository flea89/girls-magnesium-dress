from rest_framework import permissions, viewsets
from api.serializers import SurveySerializer
from core.models import Survey
from rest_framework.permissions import IsAuthenticated


class SurveyViewSet(viewsets.ModelViewSet):
    """
    API endpoit for survey resource.
    """
    serializer_class = SurveySerializer
    queryset = Survey.objects.all()

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        We want to allow qualtrics users to list the companies only.
        """
        if self.action in ('list',):
            return [IsAuthenticated()]
        else:
            return super(SurveyViewSet, self).get_permissions()

    def get_queryset(self):
        """
        Returns the unique survey given his uid or an empty list.
        We don't need to expose all the Surveys for now.
        """
        queryset = Survey.objects.all()
        uid = self.request.query_params.get('uid', None)
        if uid is not None:
            queryset = queryset.filter(uid=uid)
        else:
            queryset = Survey.objects.none()
        return queryset

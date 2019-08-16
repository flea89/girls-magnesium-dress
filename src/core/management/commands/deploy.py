from os.path import dirname, join
from subprocess import check_call
from django.core.management import call_command
from django.core.management.base import BaseCommand
from google import appengine


APP_CFG = join(dirname(dirname(appengine.__path__[0])), "appcfg.py")
STAGING_APP_ID = 'gweb-digitalmaturity-staging'
PROD_APP_ID = 'gweb-digitalmaturity'


def run_deployment(application, version, with_settings):
    call_command("build", settings=with_settings)
    check_call([APP_CFG, "update", "--no_cookies", "-A", application, "-V", version, "./src"])


class Command(BaseCommand):
    help = 'Deploys a new version of the DMB app'

    def add_arguments(self, parser):
        parser.add_argument('--prod', action='store_true', default=False)
        parser.add_argument('app-version')

    def handle(self, *args, **options):
        version = options['app-version']
        if options['prod']:
            print("Starting production deployment..")
            application = PROD_APP_ID
        else:
            print("Starting staging deployment..")
            application = STAGING_APP_ID
        run_deployment(application, version, options['settings'])

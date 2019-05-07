"""Handles interacting with the Google Sheets API."""
from djangae import environment
from django.conf import settings
from google.appengine.api import memcache, urlfetch

import httplib2
from apiclient import discovery
from oauth2client.contrib.appengine import AppAssertionCredentials


_SHEETS_SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive'


def sheets_api_factory(scope=_SHEETS_SCOPE):
    """Builds a Sheets API client."""
    urlfetch.set_default_fetch_deadline(60)
    credentials = AppAssertionCredentials(scope)
    http = credentials.authorize(httplib2.Http(memcache))
    return discovery.build('sheets', 'v4', http=http)


def drive_api_factory(scope=_DRIVE_SCOPE):
    """Builds a Drive API client."""
    urlfetch.set_default_fetch_deadline(60)
    credentials = AppAssertionCredentials(scope)
    http = credentials.authorize(httplib2.Http(memcache))
    return discovery.build('drive', 'v3', http=http)


def export_data(headers, rows):
    sheets_api = sheets_api_factory()
    spreadsheet = {
        'properties': {
            'title': "Test"
        }
    }
    spreadsheet = sheets_api.spreadsheets().create(body=spreadsheet).execute()

    print("Spreadsheet created at {}".format(spreadsheet['spreadsheetUrl']))

    sheet = _clear_sheets_and_create_new_one(spreadsheet)
    _write_headers_to_sheet(spreadsheet, sheet, headers)
    _write_rows_to_sheet(spreadsheet, sheet, rows)
    share_with(spreadsheet)


def _clear_sheets_and_create_new_one(spreadsheet):
    sheets_api = sheets_api_factory()
    existing_sheet_ids = (s['properties']['sheetId'] for s in spreadsheet['sheets'])

    requests = []
    requests.extend(
        [{'addSheet': {'properties': {'hidden': False}}}]
    )
    requests.extend(
        [{'deleteSheet': {'sheetId': sheet_id}} for sheet_id in existing_sheet_ids]
    )

    body = {'requests': requests}

    response = sheets_api.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet['spreadsheetId'], body=body
    ).execute()

    sheet = response['replies'][0]['addSheet']['properties']

    return sheet


def _write_headers_to_sheet(spreadsheet, sheet, headers):
    sheets_api = sheets_api_factory()

    body = {'values': [headers]}

    sheets_api.spreadsheets().values().append(
        spreadsheetId=spreadsheet['spreadsheetId'],
        range=sheet['title'],
        body=body,
        valueInputOption='RAW',
    ).execute()


def _write_rows_to_sheet(spreadsheet, sheet, rows):
    sheets_api = sheets_api_factory()

    body = {'values': rows}

    sheets_api.spreadsheets().values().append(
        spreadsheetId=spreadsheet['spreadsheetId'],
        range=sheet['title'],
        body=body,
        valueInputOption='RAW',
    ).execute()


def share_with(spreadsheet):
    drive_api = drive_api_factory()
    permission_response = drive_api.permissions().create(
        fileId=spreadsheet['spreadsheetId'],
        sendNotificationEmail=False,
        # transferOwnership=True,
        body={
            "type": "user",
            "emailAddress": "marco.azzalin@potatolondon.com",
            "role": "writer",
        }
    ).execute()

    print("Permission response:  {}".format(permission_response))



class Trix(object):
    '''Create a Trix that can be exported.'''

    def __init__(self, headers, rows):
        '''
        headers is a list of str
        rows is a list of list of JSON serializable objects.
        '''
        sheets_api = sheets_api_factory()
        spreadsheet = {
            'properties': {
                'title': "Test"
            }
        }
        self.spreadsheet = sheets_api.spreadsheets().create(body=spreadsheet).execute()

        print("Spreadsheet created at {}".format(self.spreadsheet['spreadsheetUrl']))

        self.headers = headers
        self.rows = rows

    def export_and_overwrite(self):
        '''Clear existing sheets and export headers and rows to default sheet.'''

        sheets_api = sheets_api_factory()
        spreadsheet_id = self.spreadsheet.get('spreadsheetId')
        spreadsheet = sheets_api.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

        sheet = self._clear_sheets_and_create_new_one(spreadsheet)
        self._write_headers_to_sheet(spreadsheet, sheet)
        self._write_rows_to_sheet(spreadsheet, sheet)
        self.share_with()

    def _clear_sheets_and_create_new_one(self, spreadsheet):
        sheets_api = sheets_api_factory()
        existing_sheet_ids = (s['properties']['sheetId'] for s in spreadsheet['sheets'])

        requests = []
        requests.extend(
            [{'addSheet': {'properties': {'hidden': False}}}]
        )
        requests.extend(
            [{'deleteSheet': {'sheetId': sheet_id}} for sheet_id in existing_sheet_ids]
        )

        body = {'requests': requests}

        response = sheets_api.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet['spreadsheetId'], body=body
        ).execute()

        sheet = response['replies'][0]['addSheet']['properties']

        return sheet

    def _write_headers_to_sheet(self, spreadsheet, sheet):
        sheets_api = sheets_api_factory()

        body = {'values': [self.headers]}

        sheets_api.spreadsheets().values().append(
            spreadsheetId=spreadsheet['spreadsheetId'],
            range=sheet['title'],
            body=body,
            valueInputOption='RAW',
        ).execute()

    def _write_rows_to_sheet(self, spreadsheet, sheet):
        sheets_api = sheets_api_factory()

        body = {'values': self.rows}

        sheets_api.spreadsheets().values().append(
            spreadsheetId=spreadsheet['spreadsheetId'],
            range=sheet['title'],
            body=body,
            valueInputOption='RAW',
        ).execute()

    def share_with(self):
        drive_api = drive_api_factory()
        permission_response = drive_api.permissions().create(
            fileId=self.spreadsheet['spreadsheetId'],
            sendNotificationEmail=False,
            # transferOwnership=True,
            body={
                "type": "user",
                "emailAddress": "marco.azzalin@potatolondon.com",
                "role": "writer",
            }
        ).execute()

        print("Permission response:  {}".format(permission_response))

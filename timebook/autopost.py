import os.path
import getpass
import ConfigParser
import urllib
import urllib2

from timebook import TimesheetRow, ChiliprojectLookupHelper

class ParthenonTimeTracker(object):
    def __init__(self, login_url, timesheet_url, timesheet_db, config, date, db):
        self.timesheet_url = timesheet_url
        self.timesheet_db = timesheet_db
        self.login_url = login_url
        self.config = self.load_configuration(config)
        self.date = date
        self.db = db

    def load_configuration(self, configfile):
        co = ConfigParser.SafeConfigParser()
        if(os.path.exists(configfile)):
            co.read(configfile)
        return co

    def get_config(self, section, option):
        try:
            return self.config.get(section, option)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError), e:
            if(option.upper().find("pass") or option[0:1] == "_"):
                return getpass.getpass("%s: " % option.capitalize())
            else:
                return raw_input("%s: " % option.capitalize())    

    def main(self):
        print "Posting hours for %s" % self.date
        self.username = self.get_config('auth', 'username')
        self.password = self.get_config('auth', 'password')

        entries = self.get_entries(self.date)
        for entry in entries:
            print entry
        opener = self.login(self.login_url, self.username, self.password)
        result = self.post_entries(opener, self.timesheet_url, self.date, entries)

    def post_entries(self, opener, url, date, entries):
        data = [
                ('__tcAction[saveTimesheet]', 'save'),
                ('date', date.strftime('%Y-%m-%d')),
                ]
        for entry in entries:
            data.append(('starthour[]', entry.start_time.strftime('%H')))
            data.append(('startmin[]', entry.start_time.strftime('%M')))
            data.append(('endhour[]', entry.end_time_or_now.strftime('%H')))
            data.append(('endmin[]', entry.end_time_or_now.strftime('%M')))
            data.append(('mantisid[]', entry.ticket_number if entry.ticket_number else ''))
            data.append(('description[]', entry.timesheet_description))
            data.append(('debug[]', '1' if entry.is_billable else '0'))
            self.db.execute("""
                REPLACE INTO entry_details (entry_id, ticket_number, billable)
                VALUES (?, ?, ?)""", (
                        entry.id,
                        entry.ticket_number,
                        1 if entry.is_billable else 0
                    ))

        data_encoded = urllib.urlencode(data)
        r = opener.open("%s?date=%s" % (url, date.strftime("%Y-%m-%d")), data_encoded)

    def get_entries(self, day):
        self.db.execute("""
            SELECT
                id,
                start_time,
                COALESCE(end_time, STRFTIME('%s', 'now')) as end_time,
                description,
                ROUND((COALESCE(end_time, strftime('%s', 'now')) - start_time) / CAST(3600 AS FLOAT), 2) AS hours
            FROM
                entry
            WHERE
                start_time > STRFTIME('%s', ?, 'utc')
                AND
                start_time < STRFTIME('%s', ?, 'utc', '1 day')
            """, (day.strftime("%Y-%m-%d"), day.strftime("%Y-%m-%d"), ))
        results = self.db.fetchall()

        helper = ChiliprojectLookupHelper(
                    username = self.username,
                    password = self.password
                )

        final_results = []
        for result in results:
            entry = TimesheetRow.from_row(result)
            entry.set_lookup_handler(helper)
            final_results.append(entry)
        return final_results

    def login(self, login_url, username, password):
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        urllib2.install_opener(opener)
        data = urllib.urlencode((
                ('username', username),
                ('password', password),
            ))
        opener.open(login_url, data)
        return opener

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        return True

import requests
import re
import hashlib
import logging
from bs4 import BeautifulSoup
import pprint

import time

pp = pprint.PrettyPrinter(indent=4)


class TPen(object):
    """ TPen acts as an abstraction layer from t-pen.org
    """

    def __init__(self, **kwa):
        """ the following keys are possible in the mandatory cfg dict

            username
            password ..... t-pen credentials
            debug ........ additional debug logging
            logfile ...... logfile location
            timeout ...... timeout when accessing t-pen
            max_errors ... give up after this many errors (used for this and that)

            init will try to login into t-pen or fail miserably
        """

        cfg = kwa.get('cfg')

        self.timeout = cfg.get('timeout')
        self.max_errors = cfg.get('max_errors')
        self.timeout_errors = 0
        self.cookies = None

        self.uri_index = cfg.get('uri_index')
        self.uri_login = cfg.get('uri_login')
        self.uri_project = cfg.get('uri_project')

        self._projects_list = []

        self._global_errors = dict(
            unexpected_content_type=0,
            bad_file=0,
            empty_response=0,
            non_ok_response=0,
            login_md5=0,
            login_text=0,
            # impossible_chars        = 0,
        )

        logging.basicConfig(
            format='%(asctime)s %(message)s',
            filename=cfg.get('logfile'),
            level=cfg.get('loglevel'),
        )

        # login in
        #
        md5_login_failed = 'b9abb18f4c42fd8321f97d38790d224d'
        login_success = 'document.location = "index.jsp";'

        d = hashlib.md5()
        logged_in = False
        errors = 0
        while not logged_in and errors < self.max_errors:

            res = self._request(
                verb='post',
                uri=self.uri_login,
                data=dict(
                    uname=cfg.get('username'),
                    password=cfg.get('password'),
                ))
            d.update(res.text.encode())

            # "well" known md5 of response returned by t-pen in case of error
            if md5_login_failed == d.hexdigest():
                self._global_errors['login_md5'] += 1
                errors += 1
                logging.error('authentication failed (md5) (try %s)' % errors)
                logging.info('bad res.cookies: %s ' % pp.pformat(res.cookies))

            # "well" known response returned by t-pen in case of success
            elif login_success not in res.text:
                self._global_errors['login_text'] += 1
                errors += 1
                logging.error('authentication failed (text) (try %s)' % errors)

                logging.info('bad res.cookies: %s ' % pp.pformat(res.cookies))

            # assuming we're logged in
            else:
                logged_in = True
                logging.info('good res.cookies: %s ' % pp.pformat(res.cookies))
                self.cookies = res.cookies

        if logged_in:
            logging.info('got %s errors logging in' % errors)
        else:
            raise UserWarning('authentication failed')

    def global_errors(self):
        return self._global_errors

    def projects_list(self):
        """ get a list of all projects of logged in account
            the list consists of dicts with the two keys label and tpen_id
        """

        if not self._projects_list:
            soup = BeautifulSoup(self._request(uri=self.uri_index).text, 'html.parser')
            table = soup.find(id='projectList')

            # link target may not change
            # projectID is supposed to be the first parameter
            #
            p = re.compile('^transcription.html\?projectID=(\d+).*')

            for tr in table.tbody.find_all('tr'):
                label = tr.get('title')
                href = tr.td.a.get('href')
                match = p.match(href)

                label and match and self._projects_list.append(dict(
                    label=tr.get('title'),
                    tpen_id=match.group(1),
                ))

        return self._projects_list

    def project(self, **kwa):
        """ get a single project
            the given project dict will be updated with a corresponding data key and returned
        """

        project = kwa.get('project')
        file_ok = False
        errors = 0
        errmsg = ""

        while errors < self.max_errors and not file_ok:
            res = self._request(self.uri_project + str(project.get('tpen_id')))

            # T-PEN sets the Content-Type header to either
            # "application/ld+json;charset=UTF-8" or "text/plain; charset=utf-8"
            # in the first case the content is encoded properly, not in the second
            #
            if res.headers.get('Content-Type') != 'application/ld+json;charset=UTF-8':
                errors += 1
                self._global_errors['unexpected_content_type'] += 1

                logging.info(
                    '[%s, "%s"] got unexpected content-type "%s", expected: "%s" (try %s)' % (
                        project.get('tpen_id'),
                        project.get('label'),
                        res.headers.get('Content-Type'),
                        'application/ld+json;charset=UTF-8',
                        errors,
                    ))
                log_res(res)
                errmsg = res.text

            else:
                file_ok = True
                project.update(data=res.text)

        if file_ok:
            logging.debug('[%s, "%s"] file looks good',
                          project.get('tpen_id'),
                          project.get('label'),
                          )
        else:
            self._global_errors['bad_file'] += 1
            logging.error('[%s, %s] skipping file',
                          project.get('tpen_id'),
                          project.get('label'),
                          )
            project.update(
                data=None,
                garbage=errmsg,
            )

        return project

    def projects(self):
        """ get all projects of logged in account
        """

        for project in self.projects_list():
            yield self.project(project=project)

    def projects_as_list(self):
        """ get all projects of logged in account
        """

        return [self.project(project=project)
                for project in self.projects_list()
                ]

    def _request(self, uri, **kwa):
        """ issues a request to the given uri and return the response as is
            defaults to GET
        """

        res = None
        ex = None
        ok = False
        errors = 0
        sleep_for = 2

        while not ok and errors < self.max_errors:
            try:
                res = self._do_request(
                    uri=uri or kwa.get('uri'),
                    verb=kwa.get('verb') or 'get',
                    data=kwa.get('data'),
                )

            except requests.exceptions.Timeout as e:
                logging.error('cought requests.exceptions.Timeout (try %s) for URI: <%s>' % (errors, uri))
                errors += 1
                ex = e
                logging.info('sleeping %s seconds' % sleep_for)
                time.sleep(sleep_for)

            else:
                ok = True
                logging.debug('requeset went ok')

        if ex:
            logging.exception(
                'cought requests.exceptions.Timeout %s times, giving up' %
                self.max_errors
            )
            raise ex

        elif not ok:
            logging.error('something went terribly wrong')
            raise UserWarning('something went terribly wrong')

        return res

    def _do_request(self, uri, **kwa):
        uri = uri or kwa.get('uri')
        verb = kwa.get('verb') or 'get'
        data = kwa.get('data')

        if verb == 'post':
            res = requests.post(
                uri,
                data=data,
                cookies=self.cookies,
                timeout=self.timeout,
            )
        elif verb == 'get':
            # XXX it is no genius idea to keep this in a rather generic _request()
            headers = dict(Accept='application/ld+json;charset=UTF-8')

            res = requests.get(
                uri,
                headers=headers,
                cookies=self.cookies,
                timeout=self.timeout,
            )
        else:
            raise UserWarning('invalid verb')

        # status-code seems always 200, body sometimes empty
        #
        if not res.ok:
            logging.error('%(verb)s to %(uri) returned status code %(code)s' % dict(
                verb=verb.upper(),
                uri=uri,
                code=res.status_code,
            ))
            self._global_errors['non_ok_response'] += 1
            log_res(res)

        if not res.text:
            logging.error(
                '%(verb)s %(uri) returned empty body (status code: %(code)s' % dict(
                    verb=verb.upper(),
                    uri=uri,
                    code=res.status_code,
                ))
            self._global_errors['empty_response'] += 1
            log_res(res)

        return res


def log_res(res):
    """ basically log the whole response
    """

    logging.debug('[last response] res.headers: %s ' % pp.pformat(res.headers))
    logging.debug('[last response] res.encoding: %s ' % res.encoding)
    logging.debug('[last response] res.status_code: %s ' % res.status_code)
    logging.debug('[last response] res.cookies: %s ' % pp.pformat(res.cookies))
    logging.debug('[last response] len (res.text): %s ' % len(res.text))
    logging.debug('[last response] res.history: %s ' % res.history)


if __name__ == '__main__':
    pass

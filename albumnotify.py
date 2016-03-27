 # -*- coding: utf-8 -*-
import requests, urllib, json, re, time, os
from lxml import etree
from datetime import datetime
import webbrowser


def file_put(filename, text):
    with open(filename, 'wb') as fp:
        fp.write(text)

def file_get(filename):
    with open(filename, 'rb') as fp:
        s = fp.read()
    return s


def get_album_type(release):
    types = [release['primary-type'] or ''] + (release['secondary-types'] or [])
    types = filter(len, map(lambda x: x.lower().encode('utf-8'), types))
    if len(types) > 1 and types[0] == 'album':
        types = types[1:]
    return ' '.join(types)

def requests_get_cached(url):
    cached_filename = 'cache/' + urllib.quote_plus(url) + ".txt"
    abs_path = os.path.join(os.getcwd(), cached_filename)
    if len(abs_path) > 240:
        cached_filename = cached_filename[:-4][:-(len(abs_path) - 240)] + '.txt'
    if not os.path.exists('cache'):
        os.mkdir('cache')
    if not os.path.exists(cached_filename):
        # https://python-musicbrainzngs.readthedocs.org/en/latest/api/#general
        # musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
        status_code = 0
        delay = 1
        retry_attempts = 10
        for i in range(retry_attempts):
            time.sleep(delay)
            delay *= 1.9
            resp = requests.get(url)

            if resp.status_code == 200:
                break
            print "Got status code #{}, retrying (attempt {}/{})...".format(resp.status_code, i+2, retry_attempts)

        if resp.status_code != 200:
            raise IOError("Can't fetch url %s" % url)

        result = resp.text.encode('utf-8')
        file_put(cached_filename, result)
    return file_get(cached_filename)

def get_lastfm_url(band):
    return 'http://www.last.fm/music/%s' % urllib.quote_plus(band)
def get_musicbrainz_url(band):
    return 'http://musicbrainz.org/search?query=%s&type=artist&method=indexed' % urllib.quote_plus(band)

def get_lastfm_scrobbles(band):
    page = requests_get_cached(get_lastfm_url(band))
    tree = etree.HTML(page)
    #items = tree.xpath('//div[@class="catalogue-scrobble-graph-top-data"]/strong/text()')
    items = tree.xpath('//div[@class="header-metadata-global-stats"]//abbr/@title')
    if len(items) < 2:
        return 0
    #return int(re.sub(r'\D', '', items[1]))
    return int(re.sub(r'\D', '', items[0]))

def get_artist_ids(band):
    js = json.loads(requests_get_cached('http://musicbrainz.org/ws/2/artist/?query=%s&fmt=json' % urllib.quote_plus(band)))
    candidates = filter(lambda x: int(x['score']) >= 85, js['artists'])
    return [x['id'] for x in candidates]

def get_albums(artist_id):
    js = json.loads(requests_get_cached('http://musicbrainz.org/ws/2/artist/%s?inc=release-groups&fmt=json' % artist_id))
    for release in sorted(js['release-groups'], key=lambda x: x['first-release-date']):
        yield release['title'].encode('utf-8'), release['first-release-date'][:4].encode('utf-8'), get_album_type(release)


def get_interesting_bands_from_file(filename):
    bandlist = file_get(filename).splitlines()
    for band in bandlist:
        artist_id = None
        m = re.match(r'^(.*) # ([-\da-f]+)$', band)
        if m:
            band, artist_id = m.groups()
        band = band.replace('/', ' ') # To/Die/For HTTP 400
        band = band.replace(' (band)', '').replace(' (группа)', '')
        band = band.replace('%C3%AB', 'ë')
        yield band, artist_id


def get_year_class(year):
    if year == '':
        return ''
    if int(year) == datetime.now().year:
        return 'this-year'
    elif int(year) == datetime.now().year - 1:
        return 'prev-year'
    return ''

def get_album_type_class(types):
    return 'worthy' if types in ['album', 'ep', 'soundtrack'] else 'unworthy'

def number_format(num):
    return '{:,}'.format(num).replace(',', '&nbsp;')


def generate_html_albums_report(interesting_bands):
    html = ['''
    <meta charset="utf-8">
    <style>
    body, table { font: 11px 'tahoma'; }
    h1 { display: inline; font: 18px 'trebuchet ms'; font-weight: normal; }
    table td { vertical-align: top; }
    .year { width: 30px; }
    .album-type { font-size: -1; width: 100px; }
    .this-year .year { color: red; }
    .prev-year .year { color: orange; }
    .unworthy { color: gray; }
    </style>
    ''']

    scrobbles_top = dict()
    html.append('Artists: %d<hr>' % len(interesting_bands))
    for band, artist_id in interesting_bands:
        print band
        artist_ids = get_artist_ids(band) if artist_id == None else [artist_id]
        scrobbles = get_lastfm_scrobbles(band)
        scrobbles_top[band] = scrobbles
        html.append('<h1><a href="%s">%s</a></h1> (<a href="%s">%s</a> plays) <small>[<a href="http://rutracker.org/forum/tracker.php?max=1&nm=%s" target="_blank">rutracker</a>]</small><br>' % (
            get_musicbrainz_url(band), band, get_lastfm_url(band), number_format(scrobbles), urllib.quote_plus(band)))
        if len(artist_ids) > 0:
            html.append('<table>')
            for title, year, release_type in get_albums(artist_ids[0]):
                html.append('<tr class="%s %s"><td class="year">%s<td class="album-type">%s<td>%s' % (
                    get_year_class(year), get_album_type_class(release_type), year, release_type, title))
            html.append('</table>')

    html.append('<hr>')
    html.append('<h1>Last.fm rating</h1>')
    html.append('<table>')
    for band, scrobbles in sorted(scrobbles_top.items(), key=lambda x: x[1], reverse=True):
        html.append('<tr><td align="right">%s<td>%s' % (number_format(scrobbles), band))
    html.append('</table>')
    return ''.join(html)


if __name__ == '__main__':
    interesting_bands = list(get_interesting_bands_from_file('bands.txt'))
    html = generate_html_albums_report(interesting_bands)
    report_filename = 'albumnotify.report.' + datetime.now().strftime('%Y-%m-%d') + '.html'
    file_put(report_filename, html)
    webbrowser.open(report_filename)

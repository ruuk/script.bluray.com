# -*- coding: utf-8 -*-
import os, requests, json
import xbmc, xbmcgui, xbmcvfs
import util

NFO = u'''<movie>
<title>{title}</title>
<sorttitle>{sort}</sorttitle>
<rating>{rating}</rating>
<runtime>{runtime}</runtime>
<plot>{plot}</plot>
<year>{year}</year>
<thumb>{thumb}</thumb>
<fanart>{fanart}</fanart>
<playcount>{watched}</playcount>
<filenameandpath>{path}</filenameandpath>
<credits></credits>
<art>
    <fanart>{fanart}</fanart>
    <poster>{thumb}</poster>
</art>
<fileinfo>
    <streamdetails>
    </streamdetails>
</fileinfo>
{collection}
{genres}
{actors}
{tags}
</movie>'''

def canceled():
    return bool(util.getGlobalProperty('EXPORT_CANCELED'))

def exporting():
    return bool(util.getGlobalProperty('EXPORTING'))

def cancel():
    util.setGlobalProperty('EXPORT_CANCELED','true')

def exportBG(category):
    if exporting(): return
    xbmc.executebuiltin("RunScript(script.bluray.com,{0},export)".format(category))

def export(results=None,category=None):
    if exporting(): return
    util.setGlobalProperty('EXPORTING','true')
    util.setGlobalProperty('EXPORT_CANCELED','')
    try:
        _export(results,category)
    finally:
        util.setGlobalProperty('EXPORTING','')
        util.setGlobalProperty('EXPORT_CANCELED','')

def _export(results=None,category=None):
    util.initAPI()

    if not results:
        try:
            cats = util.getCollectionCategories(int(category))
            results = util.API.getCollection(categories=cats)
            print repr(category),repr(results), repr(cats)
        except util.bluraycomapi.LoginError: #TODO: Implement with notifiacation
            #error = 'Unknown'
            #if e.error == 'userpass': error = 'Bad Blu-ray.com name or password.'
            #xbmcgui.Dialog().ok('Error','Login Error:','',error)
            return

    tag = u'<tag>{0}</tag>'
    genre = u'<genre>{0}</genre>'
    actor = u'    <actor><name>{name}</name><role>{role}</role><thumb>{thumb}</thumb></actor>\n'
    set_ = u'<set>{0}</set>'

    path = util.getSetting('export_path')
    if not path or not xbmcvfs.exists(path):
        path = xbmcgui.Dialog().browse(3,util.T(32054),'files')
        if not path: return
        util.ADDON.setSetting('export_path',path)
    sep = u'/'
    if '\\' in path: sep = u'\\'
    video = os.path.join(xbmc.translatePath(util.ADDON.getAddonInfo('path')).decode('utf-8'),'resources','video.mp4')
    baseTags = tag.format('blu-ray.com')
    if util.getSetting('export_offline_tag',True):
        baseTags += tag.format('offline')

    genreTable = {}
    for g in util.API.genres: genreTable[g[2]] = g[1]
    catTable = {}
    for c in util.API.categories: catTable[c[0]] = c[1]

    total = float(len(results))
    progress = xbmcgui.DialogProgressBG()
    progress.create(util.T(32051))

    import tmdbsimple as tmdb
    tmdb.API_KEY = '99ccac3e0d7fd2c7a076beea141c1057'
    config = tmdb.Configuration()
    config.info()
    tmdbBaseImageURL = config.images['base_url'] + u'original{0}'
    try:
        for idx,r in enumerate(results):
            progress.update(int((idx/total)*100),r.title,' ')
            if canceled() or xbmc.abortRequested: return

            searchTitle = r.titles[0].replace('3D','').strip()

            cleanTitle = cleanFilename(r.title)

            fanart = ''

            #Write .strm file
            f = xbmcvfs.File(path+sep+u'{0}.strm'.format(cleanTitle),'w')
            f.write(video.encode('utf-8'))
            f.close()

            #Write .nfo file
            if util.getSetting('export_write_nfo',True):
                tags = baseTags
                tags += tag.format(catTable.get(r.categoryID,''))
                if r.is3D: tags += tag.format('3D')

                genres = ''
                for i in r.genreIDs:
                    if i in genreTable:
                        genres += genre.format(genreTable[i])

                actors = ''
                collection = ''
                plot = ''
                if util.getSetting('export_get_tmdb',True):
                    from xml.sax.saxutils import escape

                    progress.update(int((idx/total)*100),r.title,u'TMDB: {0}'.format(searchTitle))
                    search = tmdb.Search()
                    tryTwice(search.movie,query=searchTitle,year=r.year)
                    if canceled() or xbmc.abortRequested: return
                    if not search.results:
                        if ':' in searchTitle:
                            searchTitle = searchTitle.split(':',1)[0]
                            progress.update(int((idx/total)*100),r.title,u'TMDB: {0}'.format(searchTitle))
                            tryTwice(search.movie,query=searchTitle,year=r.year or None)
                            if canceled() or xbmc.abortRequested: return
                    if search.results:
                        movie = tmdb.Movies(search.results[0]['id'])
                        tryTwice(movie.info,append_to_response='credits')
                        if canceled() or xbmc.abortRequested: return
                        fanart = movie.backdrop_path and tmdbBaseImageURL.format(movie.backdrop_path) or ''
                        if movie.belongs_to_collection:
                            collection = set_.format(escape(movie.belongs_to_collection['name']))
                            if r.uniqueMovies:
                                bd = movie.belongs_to_collection['backdrop_path']
                                fanart = bd and tmdbBaseImageURL.format(bd) or fanart
                        for c in movie.credits.get('cast',[]):
                            actors += actor.format(name=escape(c['name']),role=escape(c['character']),thumb=escape(tmdbBaseImageURL.format(c['profile_path'])))
                        plot = movie.overview

                f = xbmcvfs.File(path+sep+u'{0}.nfo'.format(cleanTitle),'w')
                f.write(
                    NFO.format(
                        title=escape(r.title),
                        sort=escape(r.sortTitle or r.title),
                        rating=r.rating.split(' ',1)[-1],
                        #plot=r.description or r.info,
                        path=escape(video),
                        runtime=r.runtime,
                        plot=escape(plot),
                        year=r.year,
                        thumb=escape(r.icon.replace('_medium.','_front.')),
                        fanart=escape(fanart),
                        watched=r.watched and '0' or '',
                        collection=collection,
                        genres=genres,
                        actors=actors,
                        tags=tags
                    ).encode('utf-8')
                )
                f.close()

            fanartOutPath = path+sep+u'{0}-fanart.jpg'.format(cleanTitle)
            if util.getSetting('export_get_fanart',True) and fanart and not xbmcvfs.exists(fanartOutPath):
                progress.update(int((idx/total)*100),r.title,u'Getting fanart')
                f = xbmcvfs.File(fanartOutPath,'w')
                try:
                    r = requests.get(fanart, stream=True)
                    if canceled() or xbmc.abortRequested: return
                    if r.status_code == 200:
                        for chunk in r.iter_content(1024):
                            f.write(chunk)
                finally:
                    f.close()

        #Tag existing movies online
        if util.getSetting('export_offline_tag',True) and util.getSetting('export_online_tag',True):
            progress.update(100,util.T(32052))
            response = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties":["tag"]}, "id": 1}')
            try:
                data = json.loads(response)
                if 'result' in data and 'movies' in data['result']:
                    for i in data['result']['movies']:
                        tags = i['tag']
                        if not 'offline' in tags and not 'online' in tags:
                            tags.append('online')
                            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params":{"movieid":%s,"tag":%s},"id": 1}' % (i['movieid'],json.dumps(tags)))
            except:
                util.ERROR()
    finally:
        progress.close()

    #Trigger library scan of export path
    if util.getSetting('export_trigger_scan',True):
        xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.Scan", "params": {"directory":"%s"}, "id": 1}' % path)

    xbmcgui.Dialog().ok(util.T(32048),'',util.T(32053).format(int(total)))

def tryTwice(func,*args,**kwargs):
    try:
        return func(*args,**kwargs)
    except:
        util.ERROR()
    xbmc.sleep(500)
    try:
        return func(*args,**kwargs)
    except:
        util.ERROR()

def cleanFilename(filename):
    import string
    import unidecode
    try:
        filename = unidecode.unidecode(filename).decode('utf8')
    except:
        util.LOG('Failed to convert chars in filename: {0}'.format(repr(filename)))
    filename = filename.replace(': ',' - ').strip()
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    return ''.join(c if c in valid_chars else '_' for c in filename)
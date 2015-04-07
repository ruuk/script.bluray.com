# -*- coding: utf-8 -*-
import os, requests, shutil, bluraycomapi
import xbmc, xbmcgui, xbmcaddon

ADDON = xbmcaddon.Addon()
T = ADDON.getLocalizedString

CACHE_PATH = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')),'cache')
LOCAL_STORAGE_PATH = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')),'local')

if not os.path.exists(CACHE_PATH): os.makedirs(CACHE_PATH)
if not os.path.exists(LOCAL_STORAGE_PATH): os.makedirs(LOCAL_STORAGE_PATH)

API = None

def LOG(msg):
    print 'Blu-ray.com: %s' % msg

def ERROR():
    import traceback
    traceback.print_exc()

def getSetting(key,default=None):
    setting = ADDON.getSetting(key)
    return _processSetting(setting,default)

def _processSetting(setting,default):
    if not setting: return default
    if isinstance(default,bool):
        return setting.lower() == 'true'
    elif isinstance(default,int):
        return int(float(setting or 0))
    elif isinstance(default,list):
        if setting: return setting.split(':!,!:')
        else: return default

    return setting

def setGlobalProperty(key,val):
    return xbmcgui.Window(10000).setProperty('script.bluray.com.{0}'.format(key),val)

def getGlobalProperty(key):
    return xbmc.getInfoLabel('Window(10000).Property(script.bluray.com.{0})'.format(key))

def initAPI():
    global API
    if API: return API
    API = bluraycomapi.BlurayComAPI(LOCAL_STORAGE_PATH)
    API.setDefaultCountryByIndex(getSetting('default_country',0))
    API.user = ADDON.getSetting('user') or None
    API.md5password = ADDON.getSetting('pass') or None

    LOG('Default country: %s' % str(API.defaultCountry).upper())

    return API

def imageToCache(src,name):
    response = requests.get(src, stream=True)
    target = os.path.join(CACHE_PATH,name)
    with open(target, 'wb') as out_file:
        shutil.copyfileobj(response.raw, out_file)
    del response
    return target

def tryTwice(func,*args,**kwargs):
    try:
        return func(*args,**kwargs)
    except:
        ERROR()
    xbmc.sleep(500)
    try:
        return func(*args,**kwargs)
    except:
        ERROR()

def getCollectionCategories(category=None,obj=None):
    if category is not None:
        default = category
    else:
        default = getSetting('default_collection',0)
        if default > 2:
            default = API.categories[default-3][0]
        else:
            default = 0 - default
        if obj: obj.lastCategory = default
    if default == 0:
        cats = []
        for ID,cat in API.categories:  # @UnusedVariable
            if getSetting('all_cat_%d' % ID,False): cats.append(ID)
        return cats
    elif default == -1:
        cats = []
        for ID,cat in API.categories:  # @UnusedVariable
            if getSetting('movies_cat_%d' % ID,False): cats.append(ID)
        return cats
    elif default == -2:
        cats = []
        for ID,cat in API.categories:  # @UnusedVariable
            if getSetting('games_cat_%d' % ID,False): cats.append(ID)
        return cats
    else:
        return [default]
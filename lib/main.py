import os, sys, shutil, requests
import xbmc, xbmcgui, xbmcaddon
import bluraycomapi

ADDON = xbmcaddon.Addon()
T = ADDON.getLocalizedString

CACHE_PATH = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')),'cache')

if not os.path.exists(CACHE_PATH): os.makedirs(CACHE_PATH)

API = None
LAST_SEARCH = ''

def LOG(msg):
	print 'Blu-ray.com: %s' % msg
bluraycomapi.LOG = LOG
	
def imageToCache(src,name):
	response = requests.get(src, stream=True)
	target = os.path.join(CACHE_PATH,name)
	with open(target, 'wb') as out_file:
		shutil.copyfileobj(response.raw, out_file)
	del response
	return target

class BaseWindowDialog(xbmcgui.WindowXMLDialog):
	def __init__(self):
		self.loading = None
		self._closing = False
		
	def loadingOn(self):
		if not self.loading: return
		self.setProperty('loading','1')
		
	def loadingOff(self):
		if not self.loading: return
		self.setProperty('loading','0')
		
	def setProperty(self,key,value):
		if self._closing: return
		xbmcgui.Window(xbmcgui.getCurrentWindowDialogId()).setProperty(key,value)
		xbmcgui.WindowXMLDialog.setProperty(self,key,value)
		
	def doClose(self):
		self._closing = True
		self.close()
	
class BluRayCategories(xbmcgui.WindowXML):
	def __init__(self,*args,**kwargs):
		xbmcgui.WindowXML.__init__(self)
	
	def onInit(self):
		self.catList = self.getControl(100)
		self.showCategories()
		
	def showCategories(self):
		items = []
		for label, icon, ID in API.getCategories():
			item = xbmcgui.ListItem(label=label,iconImage=icon)
			item.setProperty('id',ID)
			items.append(item)
		self.catList.addItems(items)
		self.setFocus(self.catList)
		
	def onClick(self,controlID):
		if controlID == 100:
			item = self.catList.getSelectedItem()
			if not item: return
			if item.getProperty('id') == 'reviews':
				openReviewsWindow()
			elif item.getProperty('id') == 'releases':
				openReviewsWindow(mode='RELEASES')
			elif item.getProperty('id') == 'deals':
				openReviewsWindow(mode='DEALS')
			elif item.getProperty('id') == 'collection':
				openReviewsWindow(mode='COLLECTION')
			elif item.getProperty('id') == 'search':
				openReviewsWindow(mode='SEARCH')
				
class BluRayReviews(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.mode = kwargs.get('mode')
		self.currentResults = []
		self.idxOffset = 0
		self.hasSearched = False
	
	def onInit(self):
		self.reviewList = self.getControl(101)
		self.loading = self.getControl(149)
		self.showReviews()
	
	def refresh(self,page=0,category=None):
		self.reviewList.reset()
		self.showReviews(page=page,category=category)
		
	def getCollectionCategories(self,category=None):
		if category is not None:
			default = category
		else:
			default = getSetting('default_collection',0)
		if default == 0:
			cats = []
			for ID,cat in API.categories:  # @UnusedVariable
				if getSetting('all_cat_%d' % ID,False): cats.append(ID)
			return cats
		else:
			return [default]
	
	def getCollectionCategoriesToShow(self,ids=False):
		cats = []
		if ids:
			for ID,cat in API.categories:
				if getSetting('used_cat_%d' % ID,False): cats.append(ID)
		else:
			for ID,cat in API.categories:
				if getSetting('used_cat_%d' % ID,False): cats.append(cat)
		return cats

	def showReviews(self,page=0,category=None):
		self.loadingOn()
		try:
			paging = (None,None)
			if self.mode == 'SEARCH':
				self.loadingOff()
				w = openWindow(BluRaySearch,'bluray-com-search.xml',return_window=True)
				self.loadingOn()
				if w.canceled:
					if not self.hasSearched: self.doClose()
					return
				if not w.keywords:
					if not self.hasSearched: self.doClose()
					return
				results = API.search(w.keywords,w.section,w.country)
				del w
				if not results:
					xbmcgui.Dialog().ok(T(32008),T(32009))
					if self.hasSearched: return
					self.doClose()
					return
				self.hasSearched = True
				self.reviewList.reset()
			elif self.mode == 'RELEASES':
				results = API.getReleases()
			elif self.mode == 'DEALS':
				results, paging = API.getDeals(page)
			elif self.mode == 'COLLECTION':
				results = API.getCollection(categories=self.getCollectionCategories(category))
				self.currentResults = results
			else:
				results, paging = API.getReviews(page)
			items = []
			if paging[0]:
				item = xbmcgui.ListItem(label=T(32005),iconImage='')
				item.setProperty('paging','prev')
				item.setProperty('page',paging[0])
				items.append(item)
				self.idxOffset = 1
				
			for i in results:
				if i._section: items.append(self.addSection(i))
				item = xbmcgui.ListItem(label=i.title,iconImage=i.icon)
				self.setUpItem(item, i)
				items.append(item)
				
			if paging[1]:
				item = xbmcgui.ListItem(label=T(32006),iconImage='')
				item.setProperty('paging','next')
				item.setProperty('page',paging[1])
				items.append(item)
				
			self.reviewList.addItems(items)
			self.setFocus(self.reviewList)
		finally:
			self.loadingOff()

	def addSection(self,i):
		item = xbmcgui.ListItem()
		item.setProperty('paging','section')
		if i._section == 'THISWEEK':
			item.setLabel(T(32017))
		else:
			item.setLabel(T(32018))
		return item
	
	def setUpItem(self,item,i):
		item.setProperty('id',i.ID)
		item.setProperty('description',i.description)
		item.setProperty('info',i.info)
		item.setProperty('genre',i.genre)
		item.setProperty('rating',i.rating)
		item.setProperty('ratingImage',i.ratingImage)
		item.setProperty('url',i.url)
		item.setProperty('flag',i.flagImage)
				
	def doMenu(self):
		if self.mode == 'COLLECTION':
			items = ['All']
			for cat in self.getCollectionCategoriesToShow(): # @UnusedVariable
				items.append(cat)
			items.append('Toggle Watched')
			idx = xbmcgui.Dialog().select('Category',items)
			if idx < 0: return
			if idx == 0:
				self.refresh(category=0)
			elif idx == len(items) - 1:
				self.toggleWatched()
			else:
				self.refresh(category=self.getCollectionCategoriesToShow(ids=True)[idx-1])
		elif self.mode == 'SEARCH':
			self.showReviews()

	def toggleWatched(self):
		self.loadingOn()
		succeeded = False
		try:
			idx = self.reviewList.getSelectedPosition()
			if idx < self.idxOffset: return
			idx += self.idxOffset
			if idx > len(self.currentResults): return
			result = self.currentResults[idx]
			result.json['watched'] = result.json.get('watched') != '1' and '1' or ''
			succeeded = API.updateCollectable(result.json)
		finally:
			self.loadingOff()
			
		if succeeded:
			item = self.reviewList.getSelectedItem()
			result.refresh()
			self.setUpItem(item, result)
			self.setFocus(self.reviewList)
		
	def onClick(self,controlID):
		if controlID == 101:
			item = self.reviewList.getSelectedItem()
			if not item: return
			if item.getProperty('paging'):
				if item.getProperty('paging') == 'section': return
				self.refresh(page=item.getProperty('page'))
			else:
				openWindow(BluRayReview, 'bluray-com-review.xml',url=item.getProperty('url'))
				
	def onAction(self,action):
		try:
			if action == 117:
				self.doMenu()
			elif action == 9 or action == 10:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
	
class BluRayReview(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.url = kwargs.get('url')
		
	def onInit(self):
		self.imagesList = self.getControl(102)
		self.altList = self.getControl(134)
		self.reviewText = self.getControl(130)
		self.infoText = self.getControl(132)
		self.loading = self.getControl(149)
		self.showReview()
	
	def reset(self,link):
		self.url = link
		self.imagesList.reset()
		self.altList.reset()
		self.reviewText.reset()
		self.infoText.reset()
		self.showReview()
		
	def showReview(self):
		self.loading.setVisible(True)
		try:
			review = API.getReview(self.url)
			self.setProperty('title', review.title)
			self.setProperty('subheading1', review.subheading1)
			self.setProperty('subheading2', review.subheading2)
			self.setProperty('flag', review.flagImage)
			self.setProperty('cover', review.coverImage)
			self.setProperty('owned',review.owned and T(32019) or '')
			self.reviewText.setText(review.review)
			
			self.infoText.setText(('[CR][B]%s[/B][CR]' % ('_' * 200)).join((review.price,review.blurayRating,review.overview,review.specifications)))
			
			items = []
			for url,url_1080p in review.images:
				item = xbmcgui.ListItem(iconImage=url)
				item.setProperty('1080p',url_1080p)
				items.append(item)
			ct = 0
			for source, url in review.historyGraphs:  # @UnusedVariable
				url = imageToCache(url,'graph%s.png' % ct)
				item = xbmcgui.ListItem(iconImage=url)
				item.setProperty('1080p',url)
				items.append(item)
				ct += 1
			self.imagesList.addItems(items)
			
			items = []
			if review.otherEditions:
				item = xbmcgui.ListItem(label=T(32015))
				item.setProperty('separator','1')
				items.append(item)
				
			for link, image, text in review.otherEditions:
				item = xbmcgui.ListItem(iconImage=image)
				item.setProperty('link',link)
				item.setProperty('text',text)
				items.append(item)
				
			if review.similarTitles:
				item = xbmcgui.ListItem(label=T(32016))
				item.setProperty('separator','1')
				items.append(item)
				
			for link, image, text in review.similarTitles:
				item = xbmcgui.ListItem(iconImage=image)
				item.setProperty('link',link)
				item.setProperty('text',text)
				items.append(item)
			self.altList.addItems(items)
			self.setFocus(self.imagesList)
		finally:
			self.loading.setVisible(False)
		
	def onClick(self,controlID):
		if controlID == 102:
			item = self.imagesList.getSelectedItem()
			if not item: return
			openWindow(ImageViewer, 'bluray-com-image.xml',url=item.getProperty('1080p'))
		elif controlID == 134:
			item = self.altList.getSelectedItem()
			if not item: return
			link = item.getProperty('link')
			if not link: return
			self.reset(link)
			
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
			
class BluRaySearch(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		self.keywords = LAST_SEARCH
		self.section = 'bluraymovies'
		self.country = 'all'
		self.canceled = True
		BaseWindowDialog.__init__(self)
		
	def onInit(self):
		self.keywordsButton = self.getControl(102)
		self.sectionList = self.getControl(100)
		self.countryList = self.getControl(101)
		self.fillSearch()
		
	def fillSearch(self):
		if LAST_SEARCH: self.keywordsButton.setLabel(LAST_SEARCH)
		lastSection = getSetting('search_last_section','')
		lastCountry = getSetting('search_last_country','')
		sectionIDX = 0
		countryIDX = 0
		
		items = []
		ct = 0
		for sid, sname in API.sections:
			item = xbmcgui.ListItem(label=sname)
			item.setProperty('sectionid',sid)
			items.append(item)
			if sid == lastSection: sectionIDX = ct
			ct+=1
		self.sectionList.addItems(items)
		items = []
		ct = 0
		for c in API.countries:
			item = xbmcgui.ListItem(label=c.get('n',''))
			item.setProperty('flag',c.get('u',''))
			ccode = c.get('c','')
			item.setProperty('country',ccode)
			items.append(item)
			if ccode == lastCountry: countryIDX = ct 
			ct+=1
		self.countryList.addItems(items)
		
		self.sectionList.selectItem(sectionIDX)
		self.countryList.selectItem(countryIDX)
		
	def getKeywords(self):
		key = xbmc.Keyboard(LAST_SEARCH,T(32007))
		key.doModal()
		if not key.isConfirmed(): return
		terms = key.getText()
		if not terms: return
		del key
		self.keywords = terms
		self.keywordsButton.setLabel(terms)
				
	def setSearch(self):
		global LAST_SEARCH
		self.canceled = False
		self.section = self.sectionList.getSelectedItem().getProperty('sectionid')
		self.country = self.countryList.getSelectedItem().getProperty('country')
		if self.keywords: LAST_SEARCH = self.keywords
		ADDON.setSetting('search_last_section',self.section)
		ADDON.setSetting('search_last_country',self.country)
			
	def onClick(self,controlID):
		if controlID == 102:
			self.getKeywords()
		elif controlID == 103:
			self.setSearch()
			self.doClose()
			
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
			

class ImageViewer(xbmcgui.WindowXMLDialog):
	def __init__(self,*args,**kwargs):
		self.url = kwargs.get('url')
		xbmcgui.WindowXML.__init__(self)
		
	def onInit(self):
		self.getControl(150).setImage(self.url)
		
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.close()
		finally:
			xbmcgui.WindowXMLDialog.onAction(self,action)

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

def updateUserPass():
	API.user = ADDON.getSetting('user') or None
	API.md5password = ADDON.getSetting('pass') or None
	
def getPassword():
	key = xbmc.Keyboard('',T(32026),True)
	key.doModal()
	if not key.isConfirmed(): return
	password = key.getText()
	if not password: return
	del key
	import hashlib
	ADDON.setSetting('pass',hashlib.md5(password).hexdigest())
	
def setGlobalSkinProperty(key,value=''):
	xbmcgui.Window(10000).setProperty('script.bluray.com-%s' % key,value)
	
def openReviewsWindow(mode=None):
	setGlobalSkinProperty('reviews_open','1')
	openWindow(BluRayReviews,'bluray-com-reviews.xml',mode=mode)
	setGlobalSkinProperty('reviews_open','0')
		
def openWindow(window_class,xml_file,return_window=False,**kwargs):
	w = window_class(xml_file , xbmc.translatePath(ADDON.getAddonInfo('path')), 'Main',**kwargs)
	w.doModal()
	if return_window:
		return w
	else:
		del w
	
def main():
	global API
	bluraycomapi.TR = {	'reviews':T(32001),
						'releases':T(32002),
						'deals':T(32003),
						'search':T(32004),
						'collection':T(32010),
						'watched':T(32011),
						'yes':T(32012)
	}
	API = bluraycomapi.BlurayComAPI()
	updateUserPass()
	openWindow(BluRayCategories,'bluray-com-categories.xml')
	
if __name__ == '__main__':
	if sys.argv[-1] == 'get_password':
		getPassword()
	else:
		main()

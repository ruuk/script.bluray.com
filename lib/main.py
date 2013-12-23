import os, shutil, requests
import xbmc, xbmcgui, xbmcaddon
import bluraycomapi

ADDON = xbmcaddon.Addon()

CACHE_PATH = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')),'cache')

if not os.path.exists(CACHE_PATH): os.makedirs(CACHE_PATH)

def imageToCache(src,name):
	response = requests.get(src, stream=True)
	target = os.path.join(CACHE_PATH,name)
	with open(target, 'wb') as out_file:
		shutil.copyfileobj(response.raw, out_file)
	del response
	return target

class BaseWindowDialog(xbmcgui.WindowXMLDialog):
	def setProperty(self,key,value):
		xbmcgui.Window(xbmcgui.getCurrentWindowDialogId()).setProperty(key,value)
		xbmcgui.WindowXMLDialog.setProperty(self,key,value)
	
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
			elif item.getProperty('id') == 'search':
				key = xbmc.Keyboard(heading='Enter Terms')
				key.doModal()
				if not key.isConfirmed(): return
				terms = key.getText()
				if not terms: return
				del key
				openReviewsWindow(search=terms)
				
class BluRayReviews(xbmcgui.WindowXMLDialog):
	def __init__(self,*args,**kwargs):
		self.search = kwargs.get('search')
		self.mode = kwargs.get('mode')
		xbmcgui.WindowXML.__init__(self)
	
	def onInit(self):
		self.reviewList = self.getControl(101)
		self.loading = self.getControl(149)
		self.showReviews()
	
	def refresh(self,page=0):
		self.reviewList.reset()
		self.showReviews(page=page)
		
	def showReviews(self,page=0):
		self.loading.setVisible(True)
		try:
			paging = (None,None)
			if self.search:
				results = API.search(self.search)
				if not results:
					xbmcgui.Dialog().ok('No Results','Search query provided no results.')
					return
			elif self.mode == 'RELEASES':
				results = API.getReleases()
			elif self.mode == 'DEALS':
				results = API.getDeals()
			else:
				results, paging = API.getReviews(page)
			items = []
			if paging[0]:
				item = xbmcgui.ListItem(label='Previous Page',iconImage='')
				item.setProperty('paging','prev')
				item.setProperty('page',paging[0])
				items.append(item)
				
			for i in results:
				item = xbmcgui.ListItem(label=i.title,iconImage=i.icon)
				item.setProperty('id',i.ID)
				item.setProperty('description',i.description)
				item.setProperty('info',i.info)
				item.setProperty('genre',i.genre)
				item.setProperty('rating',i.rating)
				item.setProperty('ratingImage',i.ratingImage)
				item.setProperty('url',i.url)
				item.setProperty('flag',i.flagImage)
				items.append(item)
				
			if paging[1]:
				item = xbmcgui.ListItem(label='Next Page',iconImage='')
				item.setProperty('paging','next')
				item.setProperty('page',paging[1])
				items.append(item)
				
			self.reviewList.addItems(items)
			self.setFocus(self.reviewList)
		finally:
			self.loading.setVisible(False)
		
	def onClick(self,controlID):
		if controlID == 101:
			item = self.reviewList.getSelectedItem()
			if not item: return
			if item.getProperty('paging'):
				self.refresh(page=item.getProperty('page'))
			else:
				openWindow(BluRayReview, 'bluray-com-review.xml',url=item.getProperty('url'))
	
class BluRayReview(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		self.url = kwargs.get('url')
		xbmcgui.WindowXML.__init__(self)
		
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
			self.setProperty('flag', review.flagImage)
			self.setProperty('cover', review.coverImage)
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
				item = xbmcgui.ListItem(label='Other Editions')
				item.setProperty('separator','1')
				items.append(item)
				
			for link, image, text in review.otherEditions:
				item = xbmcgui.ListItem(iconImage=image)
				item.setProperty('link',link)
				item.setProperty('text',text)
				items.append(item)
				
			if review.similarTitles:
				item = xbmcgui.ListItem(label='Similar')
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
			

class ImageViewer(xbmcgui.WindowXMLDialog):
	def __init__(self,*args,**kwargs):
		self.url = kwargs.get('url')
		xbmcgui.WindowXML.__init__(self)
		
	def onInit(self):
		self.getControl(150).setImage(self.url)
		
def setGlobalSkinProperty(key,value=''):
	xbmcgui.Window(10000).setProperty('script.bluray.com-%s' % key,value)
	
def openReviewsWindow(search=None,mode=None):
	setGlobalSkinProperty('reviews_open','1')
	openWindow(BluRayReviews,'bluray-com-reviews.xml',search=search,mode=mode)
	setGlobalSkinProperty('reviews_open','0')
		
		
def openWindow(window_class,xml_file,**kwargs):
	w = window_class(xml_file , xbmc.translatePath(ADDON.getAddonInfo('path')), 'Main',**kwargs)
	w.doModal()
	del w
	
if __name__ == '__main__':
	API = bluraycomapi.BlurayComAPI()
	openWindow(BluRayCategories,'bluray-com-categories.xml')

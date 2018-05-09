#encode: utf-8
#coding: utf-8
from selenium import webdriver
import selenium.common.exceptions as EX
import urllib
import time
from requests_html import HTML
import re
import pathlib
import os
import sqlite3 as DB
import hashlib as hashlib
import traceback
from colorama import init
from colorama import deinit
from colorama import Fore
import copy

"""每加载一次，就下载一次"""

class Tofo(object):
    def __init__(self, name, savedir=None):
        init()
        self._browser = webdriver.Chrome()
        self._user_id = name
        self._user_normal = name.replace('.','')
        self._dir = './users/'+self._user_normal
        self._to_download_cards = []
        self._current_total = 0
        self._total = 'null' # _all
        self._downd = 0
        self._table = self._user_normal
        if self._table[0] in ['1','2','3','4','5','6','7','8','9','0']:
            self._table = 'p'+self._table
        self._db = './database/'+self._user_normal+'.db'
        self._log = time.strftime('./log/%Y_%m_%d_%H_%M_%S.log',time.localtime(time.time()))
        user_path = pathlib.Path(self._dir)
        if not user_path.exists():
            pathlib.os.mkdir(self._dir)
        db_path = pathlib.Path(self._db)
        if not db_path.exists():
            db = open(self._db,'wb')
            db.close()
            db = DB.connect(self._db)
            sql = '''CREATE TABLE {0} (
                        name CHAR NOT NULL UNIQUE,
                        hash CHAR NOT NULL UNIQUE,
                        pic BINARY NOT NULL UNIQUE,
                        ext CHAR NOT NULL)'''.format(self._table)
            db.cursor().execute(sql)
            db.commit()
            db.close()
        self._loading_refresh_time = 0
        self._to_download_src = ''
        self._modal_close_button = ''
        self._pre_cards = []

    def Log(self, what):
        tm = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
        tmp = "[{0}] [{1}] [{2}个帖子] {3}".format(tm, self._user_id, self._total, what)
        open(self._log,'a',encoding='utf8').write(tmp+'\n')
        tm = Fore.LIGHTCYAN_EX+tm+Fore.RESET
        user = Fore.GREEN+self._user_id+Fore.RESET
        coun = Fore.LIGHTMAGENTA_EX+self._total.strip()+Fore.RESET
        what = what.replace('error',Fore.LIGHTRED_EX+'error'+Fore.RESET)
        what = what.replace('warning',Fore.LIGHTRED_EX+'error'+Fore.RESET)
        what = what.replace('ignore', Fore.LIGHTYELLOW_EX+'ignore'+Fore.RESET)
       
        rstr = r'\d+\.jpg'
        pattern = re.compile(rstr)
        emm = pattern.search(what)
        if emm != None:
            r = emm.group()
            what = what.replace(r,Fore.LIGHTGREEN_EX+r+Fore.RESET)
        
        rstr = r'\d+\.mp4'
        pattern = re.compile(rstr)
        emm = pattern.search(what)
        if emm != None:
            r = emm.group()
            what = what.replace(r,Fore.LIGHTGREEN_EX+r+Fore.RESET)
        
        rstr = r'\d+\/\d+'
        pattern = re.compile(rstr)
        emm = pattern.search(what)
        if emm != None:
            r = emm.group()
            what = what.replace(r,Fore.LIGHTMAGENTA_EX+r+Fore.RESET)
        
        tmp = "[{0}] [{1}] [{2}个帖子] {3}".format(tm, user, coun, what)        
        print(tmp)

    # 访问该用户的主页
    def step_1(self):
        try:
            url = 'https://tofo.me/'+self._user_id
            self.Log('[step_1] getting <%s>'%url)
            self._browser.get(url)
            time.sleep(10)
        except:
            self.Log('[step_1] [error] %s'%traceback.format_exc())
            raise DownloadInterrupt('[step_1] [error] download interrupt')
   
    # 分析一下总共有多少帖子
    def step_2(self):
        total_xpath = '/html/body/div[1]/div[1]/div[2]/div[1]/div[3]'
        try:
            total_div = self._browser.find_element_by_xpath(total_xpath)
            text = total_div.text
            self._total = text.replace('帖子','').strip().replace('千','000')
            self.Log('[step_2] total <%s> 个帖子'%self._total)
        except:
            self.Log('[step_2] [error] %s'%traceback.format_exc())
            raise DownloadInterrupt('[step_2] [error] download interrupt')

    # 去除广告项和下载过的项目
    def _step_3_1(self, cards):
        now_cards = []
        for card in cards:
            card_id = card.get_attribute('id')
            pattern = re.compile(r'^gridItem_\d+$')
            if pattern.match(card_id) != None:# 如果该项不是广告
                src_id = card_id.replace('gridItem_','')
                now_cards.append(src_id)
                sql = 'SELECT name FROM {0} WHERE name="{1}"'.format(self._table, src_id)
                conn = DB.connect(self._db)
                curs = conn.cursor()
                curs.execute(sql)
                conn.commit()
                resl = curs.fetchall()
                conn.close()# 则查询一下数据库，看该图片是否已经下载过了
                if len(resl) == 0:# 如果没有下载，则添加到当前待下载列表
                    self._to_download_cards.append(card)
                else:
                    current = self._how_many_downd()
                    self.Log('[step_3.1] [ignore] [{0}/{1}] ID <{2}> has been downloaded'.format(current,self._total, src_id))
            else:
                self.Log('[step_3.1] [ignore] found advertising <%s>'%card_id)
        self._pre_cards.sort()
        now_cards.sort()
        if self._pre_cards != now_cards:
            self._pre_cards = copy.deepcopy(now_cards)
        else:
            raise DownloadInterrupt('[step_3.1] [error] load more failed in <step_5>')
    
    # 获取当前已加载的需要下载的图片预览cards
    def step_3(self):
        cards = []
        try:
            cards = self._browser.find_elements_by_css_selector('div[id^="gridItem_"]')
        except EX.NoSuchElementException:
            time.sleep(5)
            self._loading_refresh_time += 1
            if self._loading_refresh_time == 6:
                self.Log('[step_3] [error] can not find any card !!!!')
                raise DownloadInterrupt('[step_3] [error] download interrupt')
            else:
                self.Log('[step_3] [warning] found no card, refreshed <%d> time.....'%self._loading_refresh_time)
                self._browser.refresh()
                self.Log('[step_3] [warning] researching......')
                time.sleep(10)
                self.step_3()
        else:
            self._step_3_1(cards)# 去除广告项和下载过的项目

    # 分析是图片还是视频
    def _step_4_1(self, card):
        try:
            card.click() # 点击card，弹出模态框
            self.Log('[step_4.1] modal opened')
        except:
            raise DownloadInterrupt('[step_4.1] [error] %s'%traceback.format_exc())
        jpg_css = '''body > div.ui.page.modals.dimmer.transition.visible.active 
                          > div > div > div:nth-child(3) > div:nth-child(1) 
                          > div > div > img:nth-child(3)'''.strip()
        mp4_css = '''body > div.ui.page.modals.dimmer.transition.visible.active 
                          > div > div > div > div:nth-child(2) > div > video'''.strip()
        jpg_modal_close_css = '''body > div.ui.page.modals.dimmer.transition.visible.active 
                                      > div > div > div:nth-child(3) > div:nth-child(2) 
                                      > div.ui.card > div:nth-child(1) > div:nth-child(1) > button'''.strip()
        mp4_modal_close_css = '''body > div.ui.page.modals.dimmer.transition.visible.active 
                                      > div > div > div > div:nth-child(1) > button'''.strip()
        try:
            self._to_download_src = self._browser.find_element_by_css_selector(jpg_css)
            self._modal_close_button = self._browser.find_element_by_css_selector(jpg_modal_close_css)
        except EX.NoSuchElementException:
            try:
                self._to_download_src = self._browser.find_element_by_css_selector(mp4_css)
                self._modal_close_button = self._browser.find_element_by_css_selector(mp4_modal_close_css)
            except EX.NoSuchElementException:
                raise DownloadContinue('[step_4.1] [error] [ignore] not img && not mp4')

    # 获取id,url,扩展名
    def _step_4_2(self, card):
        id_ = card.get_attribute('id').replace('gridItem_','')
        url = self._to_download_src.get_attribute('src')
        ext = url.split('.')[-1]
        return id_, url, ext

    # 请求真实地址并下载元数据
    def _step_4_3(self, url):
        headers = {
            'Host': 'x.gto.cc',
            'Connection': 'keep-alive',
            'Referer': 'https://tofo.me/'+self._user_id,
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36'
        }
        try:
            req = urllib.request.Request(url=url,headers=headers)
            data = urllib.request.urlopen(req).read()
        except urllib.error.HTTPError:
            self.Log('[step_4.3] [error] %s'%traceback.format_exc())
            raise DownloadInterrupt('[step_4.3] [error] HTTPError')
        except urllib.error.URLError:
            self.Log('[step_4.3] [error] %s'%traceback.format_exc())
            raise DownloadInterrupt('[step_4.3] [error] URLError')
        else:
            return data

    # 保存到本地
    def _step_4_4(self,data,id_,ext):
        name = id_+'.'+ext
        fl = open(self._dir+"/"+name, "wb")
        fl.write(data)
        fl.flush()
        fl.close()

    # 保存到数据库
    def _step_4_5(self, id_, ext):
        name = id_+'.'+ext
        data = open(self._dir+'/'+name, 'rb').read()
        sha512 = hashlib.sha3_512(data).hexdigest()
        sql = 'INSERT INTO {0} VALUES (?,?,?,?)'.format(self._table)
        conn = DB.connect(self._db)
        curs = conn.cursor()
        try:
            curs.execute(sql,(id_, sha512, data, ext))
            conn.commit()
        except DB.IntegrityError:
            pass
        finally:
            conn.close()
            time.sleep(2)
            current = self._how_many_downd()
            self.Log('[step_4] [{0}/{1}] <{2}> downloaded'.format(current, self._total, name))

    # 下载当前已加载的图片
    def step_4(self):
        self._current_total = len(self._to_download_cards)
        self.Log('[step_4] now found <%d> cards to download'%self._current_total)
        for card in self._to_download_cards:
            try:
                self._step_4_1(card)
            except DownloadContinue as ex:
                self.Log(ex.msg)
                continue
            except:
                self.Log('[step_4] [error] %s'%traceback.format_exc())
                continue
            else:
                id_, url, ext = self._step_4_2(card)
                self.Log('[step_4] start downloading <%s>'%(id_+'.'+ext))
                data = self._step_4_3(url)
                self._step_4_4(data, id_, ext)
                self._step_4_5(id_, ext)
                self._to_download_cards = []
                try:
                    self._modal_close_button.click()# 关闭模态框
                    self.Log('[step_4] modal closed')                    
                except:
                    raise DownloadInterrupt('[step_4] [error] %s'%traceback.format_exc())
    
    # 关闭模态框后，继续加载更多
    def step_5(self):
        script = 'window.scrollTo(0,document.body.scrollHeight)'
        self._browser.execute_script(script)# 滚动到页面底部
        src = self._browser.page_source# 先看一下还有没有加载更多的button
        html = HTML(html=src)
        buttons = html.xpath('//*[@id="app"]/div/div[2]/div/div[2]/button')
        if len(buttons) == 0:# 如果没有，说明加载完了
            raise DownloadOver('[step_5] download is over')
        else:
            select = '//*[@id="app"]/div/div[2]/div/div[2]/button'
            try:
                more_button = self._browser.find_element_by_xpath(select)
                more_button.click()
                self.Log('[step_5] <more button> clicked, waiting for load more pics......')
                time.sleep(10)
            except EX.NoSuchElementException:
                raise DownloadInterrupt('[step_5] [error] can not find <more button>')
    
    def Close(self):
        self._browser.close()

    def _how_many_downd(self):
        sql = 'SELECT ext FROM {0}'.format(self._table)
        conn = DB.connect(self._db)
        curs = conn.cursor()
        curs.execute(sql)
        conn.commit()
        resl = curs.fetchall()
        count = len(resl)
        return count

    def Go(self):
        try:
            self.step_1()
            self.step_2()
            while True:
                self.step_3()
                self.step_4()
                self.step_5()
        except DownloadInterrupt as ex:
            self.Log(ex.msg)
            self._browser.close()            
        except DownloadOver as ex:
            self.Log(ex.msg)
            self._browser.close()

class DownloadOver(Exception):
    def __init__(self, msg):
        Exception.__init__(self,msg)
        self.msg = msg

class DownloadInterrupt(DownloadOver):
    pass

class DownloadContinue(DownloadInterrupt):
    pass

if __name__ == '__main__':
    downloaded = []
    users = ['rockchaeeun', 'frombeginning_', 'pei716', 'candyballviion', 'kaokaowawa', 'lukkanaaum','hinako_sano',
             'jennachew_', 'chubby_wei', 'shacylin', 'bunny.eveava', 'monicalove0104', 'bluesister822', 'iwantmylauren',
             '524.__', 'jn.1205', 'ange_la00', 'p11q22pq', 'rainie77','juliamisakii', 'sdgogolin','namphungbwk', 'karry1230',
             'jenna_chew','sylviawang1105','gu_zhui', 'mint_chalida','june0114','cr5p__br', 'gracechowwwww',
             'florenslilium', 'cyawen109','clare_1227', 'preawwnp', 'chopperting', 'sandrawiller', 'bulky_girl',
             'tunamayo0113', 'yumibb8888', 'evelyn1998_', 'chencaicing', 'serenaaaaalin', 'bei_jhu_','cherryq_official', 'wenyu1025', 
             'iam_youngeun', 'avril_zhan', 'jolina0711', 'peiyu0515', 'beauty_body_bb', 'saki_yanase', '__leeheeeun__',
             'bunny.eveava', 'tiffanylin9000', 'piamuehlenbeck', 'shi_orii', 'joeychua8', 'sunmiub', 'fearythanyarat',
             'maggiewu1008','qtfreet','callmemiermier','nancy120578', 'hsia.vv','xinni0312__','siawase726','tamara1228',
             'coxyii','blueblueberryy','daxibb','vkzhou','oresama649284',
             'x_mini_x_','sora_pppp','l92833','yui_xin_', 'cxxsomi','shinodamariko3','chopperting','alicebambam',
             'ww2en','vivihsu0317','djsiena','p11q22pq','shacylin', 'baby_bin47','ysubini','momokoogihara','llu_lllu_',
             'tt_scarlett','crystal1lee','maybe_iamawesome', 'djxin_tw','nai.nnn','jocelynkao','dorachai','peipei321_',
             'pattylove913','ago928','pepe_l','keemdani','sprite0719ss', 'chi_7_7_','han48ox','ppparis_zhou','bivi_0420','bbooxlok',
             'mickeymyca','mongwoen','gina_jiang_', 'lenababy.14','kirakuoxx','kuonini_baby','charlott1120',
             'b__728ao','monnnw','fje0126','missjoeechong','shu_schumi', 'sylvia.suuu','hannah_wang_lucky','bella_ypt','chelsea_a',
             'hycccci','miziooo','huangacan','baddoll_com','applell213', '33kwok','xyweii','berries99','sibellemiaow',
             'yanbabe123','uccu0323','evelyn1998_','warwu','bobeyiyi', 'betty50153','eggroll0616','meiabby',
             'aurorawang0923', 'piyo_na_ri_', 'mumumuaaa','ageless_underwear'
    ]
    users = list(set(users))
    for user in users:
        tofo = Tofo(user)
        try:
            tofo.Go()
        except:
            tofo.Log('[error] [main] {0}'.format(traceback.format_exc()))
            tofo.Close()
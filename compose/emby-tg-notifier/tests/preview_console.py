"""Local-only synthetic console fixture; never connects to Telegram or Emby."""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from test_console import ConsoleTests, context, m

fixture=ConsoleTests()
fixture.setUp()
fixture.server['name']='惹咪之北影视服_HDZ'
data=context(fixture.server)
data['routes']=[{'id':1,'name':'JAV 入库通知','library_name':'JAV','library_id':'44','chat_id':'@example_channel','enabled':1}]
app=FastAPI()

@app.get('/',response_class=HTMLResponse)
def page():
    return m.templates.get_template('console.html').render(**data)

app.add_api_route('/console-mark.png',m.console_mark)
app.add_api_route('/console-eye.svg',m.console_eye)

@app.get('/api/servers/1/webhook-status')
def status():
    return {'ok':True,'status':None}

@app.post('/servers/1/save')
async def save(request:Request):
    values=await request.form()
    assert values['emby_api_key']=='test-key'
    assert values['tg_binding_bot_token']=='test-bot'
    assert values['tv_batch_minutes']=='17'
    return {'ok':True,'message':'服务器设置已保存','server_name':values['name']}

if __name__=='__main__':
    uvicorn.run(app,host='127.0.0.1',port=8799)

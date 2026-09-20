const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:1000});
   await page.goto('http://127.0.0.1:8799');
   await page.locator('.brand img').evaluate(img=>img.decode());
   assert.equal(await page.locator('form form').count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert.equal(await page.locator('#embyKey').getAttribute('type'),'password');
   assert.equal(await page.locator('#current-password').isVisible(),false);
   await page.getByRole('button',{name:'账号设置',exact:true}).click();
   assert.equal(await page.locator('#current-password').isVisible(),true);
   await page.locator('#current-password').fill('fixture-password');
   await page.route('**/settings/login',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({ok:false,message:'当前密码不正确'})}));
   await page.getByRole('button',{name:'保存账号设置',exact:true}).click();
   await page.waitForFunction(()=>document.getElementById('accountNotice').textContent==='当前密码不正确');
   await page.screenshot({path:path.resolve(__dirname,'../../../outputs/account-'+width+'.png')});
   await page.getByRole('button',{name:'关闭账号设置',exact:true}).click();
   await page.waitForFunction(()=>document.getElementById('current-password').value==='');
   await page.getByRole('button',{name:'账号设置',exact:true}).click();
   await page.keyboard.press('Escape');
   await page.locator('#accountDialog').waitFor({state:'hidden'});
   const values=await page.locator('#serverSettings').evaluate(form=>Object.fromEntries(new FormData(form)));
   assert.equal(values.emby_api_key,'test-key');assert.equal(values.tg_binding_bot_token,'test-bot');
   await page.locator('#libraryChoice').click();
   await page.locator('#librarySearch').fill('不存在');
   assert.equal(await page.locator('#libraryEmpty').isVisible(),true);
   await page.locator('#librarySearch').fill('JAV');
   await page.locator('.library-option:visible').click();
   assert.equal(await page.locator('#libraryId').inputValue(),'44');
   assert.equal(await page.locator('#libraryDialog').isVisible(),false);
   await page.locator('#libraryChoice').click();
   await page.keyboard.press('Escape');
   await page.locator('#batchMinutes').fill('17');
   await page.getByRole('button',{name:'保存服务器设置',exact:true}).click();
   await page.waitForFunction(()=>document.getElementById('saveState').textContent==='已保存');
   await page.evaluate(()=>scrollTo(0,0));
   await page.screenshot({path:path.resolve(__dirname,'../../../outputs/console-'+width+'.png'),fullPage:true});
   console.log('PASS viewport',width,'form ownership, save, modal search/select/escape, no overflow');
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

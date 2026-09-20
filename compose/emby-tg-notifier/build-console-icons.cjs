const fs = require('node:fs');
const path = require('node:path');
const { Eye } = require('lucide');
const escape = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const body = Eye.map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([k,v]) => `${k}="${escape(v)}"`).join(' ')}/>`).join('');
fs.writeFileSync(path.join(__dirname,'app/downloads/console-eye.svg'), `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#f2f5f4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`);

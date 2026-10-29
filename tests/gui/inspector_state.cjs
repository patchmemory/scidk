// Exercise shipped event handlers, including async stale-result protection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.hidden = false; this.textContent = ''; this.children = []; this.attrs = {}; this.classes = new Set(); this.classList = {toggle:(k,on)=>on ? this.classes.add(k):this.classes.delete(k)}; }
  setAttribute(k,v) {this.attrs[k]=v;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren() {this.children=[];this.textContent='';}
}
const ids = new Map();
const element = id => {if(!ids.has(id)) ids.set(id,new Element()); return ids.get(id);};
const tabs = ['Metadata','Annotations','Provenance'].map(tab => {const e = new Element();e.dataset={inspectorTab:tab};return e;});
const handlers = {};
const requests = [];
let resolveAnnotations;
const document = {getElementById:element,querySelector:()=>element('browser'),querySelectorAll:()=>tabs,createElement:()=>new Element(),addEventListener:(k,v)=>handlers[k]=v};
const fetch = async url => {
  requests.push(url);
  if(url.includes('/annotations?')) return new Promise(resolve=>resolveAnnotations=()=>resolve({ok:true,json:async()=>({items:[{label:'OLD'}]})}));
  return {ok:true,json:async()=>url.includes('/nodes/search') ? {results:[{element_id:'ds:1',name:'Study',properties:{nested:{x:1}}}]} : [{id:'f1',path:'/raw.xml'}]};
};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'), {document,window:{SCIDK_BASE:'/scidk'},fetch});
(async()=>{
  await new Promise(setImmediate);
  element('gui-datasets-tab').onclick();
  element('dataset-query').value='Study';
  await element('dataset-search').onsubmit({preventDefault(){}});
  element('dataset-results').children[0].onclick();
  assert.equal(element('inspector-title').textContent,'Dataset: Study');
  assert.equal(element('dataset-sharing').hidden,false);
  element('inspector-expand').onclick();
  assert.equal(element('inspector-expand').attrs['aria-expanded'],'true');
  tabs[1].onclick();
  element('gui-files-tab').onclick();
  handlers['scidk:inspect']({detail:{kind:'file',key:'/file',record:{name:'file'}}});
  assert.equal(element('dataset-sharing').hidden,true);
  tabs[0].onclick();
  resolveAnnotations();
  await new Promise(setImmediate);
  assert.equal(element('inspector-title').textContent,'File / folder: file');
  assert.equal(element('inspector-content').textContent,'');
  element('gui-datasets-tab').onclick();
  assert.equal(element('inspector-title').textContent,'Dataset: Study');
  assert.equal(element('inspector-expand').attrs['aria-expanded'],'true');
  assert.equal(tabs[0].attrs['aria-selected'],'true');
  element('inspector-close').onclick();
  assert.equal(element('shared-inspector').hidden,true);
  assert(!requests.some(url=>url.includes('nih_dms')||url.includes('/chat')));
  assert(requests.some(url=>url.includes('label=Dataset')));
})().catch(error=>{console.error(error);process.exitCode=1;});

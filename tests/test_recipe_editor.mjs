import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source = readFileSync(new URL('../custom_components/grocery_learning/frontend/local-list-assist-panel.js', import.meta.url), 'utf8');
const classSource = source.slice(source.indexOf('class LocalListAssistPanel extends'), source.indexOf('customElements.define("local-list-assist-panel"'));
const Panel = vm.runInNewContext(classSource + '\nLocalListAssistPanel;', {
  LitElement: class {requestUpdate() {}}, css:()=>'',
});
function panel() {
 const p = new Panel();
 p._state={meals:[{id:'dinner',name:'Dinner',image_id:'a'.repeat(64),source_url:'https://example.com/recipe'}]};
 return p;
}
test('editing preserves existing image; remove explicitly clears it', async()=>{
 const p=panel(); let sent;
 p.act=async v=>{sent=v;return {ok:true}};
 p.openMealEditor('dinner');await p.saveMeal();
 assert.equal('image_data' in sent,false);
 assert.equal(sent.source_url,'https://example.com/recipe');
 p.openMealEditor('dinner');p._drafts.mealImageData='';await p.saveMeal();
 assert.equal(sent.image_data,'');
});
test('failed saves retain the editor and uploaded photo',async()=>{
 const p=panel();p.openMealEditor('dinner');p._drafts.mealImageData='photo';
 p.act=async()=>({ok:false});await p.saveMeal();
 assert.equal(p._mealEditorId,'dinner');assert.equal(p._drafts.mealImageData,'photo');
});
test('recipe import captures image and source; failure warning preserves recipe',async()=>{
 const p=panel();p.openMealEditor('new');p._drafts.recipeUrl='https://example.com/recipe';
 p.api=async()=>({ok:true,recipe:{name:'Imported',ingredients:['rice'],image_data:'photo'},source_url:'https://example.com/recipe'});
 await p.importRecipe();assert.equal(p._drafts.mealImageData,'photo');assert.equal(p._drafts.mealSourceUrl,'https://example.com/recipe');
 p._drafts.recipeUrl='https://example.com/other';p.api=async()=>({ok:true,recipe:{name:'No photo'},image_warning:'Photo unavailable'});
 await p.importRecipe();assert.equal(p._drafts.mealName,'No photo');assert.equal(p._recipeImportError,'Photo unavailable');
});
test('late imports cannot overwrite a different editor',async()=>{
 const p=panel();p.openMealEditor('new');p._drafts.recipeUrl='https://example.com/recipe';
 let finish;p.api=()=>new Promise(resolve=>{finish=resolve});
 const pending=p.importRecipe();p.closeMealEditor();p.openMealEditor('dinner');
 finish({ok:true,recipe:{name:'Wrong meal',image_data:'photo'}});await pending;
 assert.equal(p._drafts.mealName,'Dinner');assert.equal(p._drafts.mealImageData,undefined);
});

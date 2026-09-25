document.addEventListener('DOMContentLoaded', () => {
  const rules = document.getElementById('rules');
  const initial = rules.value;
  const prompt = document.getElementById('prompt');
  const editor = window.CodeMirror ? CodeMirror.fromTextArea(rules, {
    mode: {name: 'javascript', json: true}, lineNumbers: true,
    lineWrapping: true, readOnly: true
  }) : null;
  let state = Object.entries(JSON.parse(initial).rules).map(([id, r]) => ({id, ...r}));
  const builder = document.getElementById('rule-builder');
  const sync = () => {
    const value = JSON.stringify({rules: Object.fromEntries(state.map(({id, ...r}) => [id, r]))}, null, 2);
    rules.value = value;
    if (editor) { editor.setValue(value); editor.save(); }
  };
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const field = (parent, label, value, update, type='text', limits={}) => {
    const wrap = el('label', label);
    const input = el(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.value = value;
    Object.assign(input, limits);
    input.addEventListener('input', () => { update(type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value); sync(); });
    wrap.append(input); parent.append(wrap); return input;
  };
  const button = (parent, text, action) => {
    const b = el('button', text, 'secondary'); b.type = 'button'; b.addEventListener('click', action); parent.append(b); return b;
  };
  function render() {
    builder.replaceChildren();
    state.forEach((r, index) => {
      const card = el('details', '', 'rule-card'); card.open = state.length === 1;
      const title = el('summary', r.label || '新しいルール'); card.append(title);
      const body = el('div', '', 'rule-body'); card.append(body);
      field(body, '表示名', r.label, v => { r.label=v; title.textContent=v || '新しいルール'; });
      const label = el('label', '判定形式'); const select = el('select');
      for (const [value, name] of [['noul','Noul'],['choice','Choice'],['score','Score']]) {
        const option=el('option',name); option.value=value; select.append(option);
      }
      select.value=r.type; label.append(select); body.append(label);
      select.addEventListener('change', () => {
        r.type=select.value; delete r.threshold; delete r.blocked_choices;
        if(r.type==='noul'){r.criteria={true:'該当する条件',false:'該当しない条件'};r.threshold=.5;}
        if(r.type==='choice'){r.criteria={allow:'許可する内容',block:'ブロックする内容'};r.blocked_choices=['block'];}
        if(r.type==='score'){r.criteria=['問題なし','軽度','重大'];r.threshold=1;}
        render(); builder.children[index].open=true;
      });
      field(body, '判定指示', r.instructions, v => r.instructions=v, 'textarea');
      if(r.type==='noul') {
        field(body,'該当の定義',r.criteria.true,v=>r.criteria.true=v,'textarea');
        field(body,'非該当の定義',r.criteria.false,v=>r.criteria.false=v,'textarea');
        field(body,'Blocked閾値（0〜1）',r.threshold,v=>r.threshold=v,'number',{min:0,max:1,step:.01});
      } else if(r.type==='choice') {
        Object.entries(r.criteria).forEach(([name, definition], pos) => {
          const box=el('div','','option-box'); body.append(box);
          let current=name;
          const input=field(box,'選択肢名',name,v=>{
            if(!v.trim() || (v!==current && Object.hasOwn(r.criteria,v))) { input.setCustomValidity('空欄・重複は使えません'); return; }
            input.setCustomValidity('');
            r.criteria=Object.fromEntries(Object.entries(r.criteria).map(([k,val])=>[k===current?v:k,val]));
            r.blocked_choices=r.blocked_choices.map(k=>k===current?v:k); current=v;
          });
          field(box,'定義',definition,v=>r.criteria[current]=v,'textarea');
          const checkLabel=el('label','', 'check-label'), check=el('input'); check.type='checkbox'; check.checked=r.blocked_choices.includes(name);
          check.addEventListener('change',()=>{r.blocked_choices=r.blocked_choices.filter(x=>x!==current);if(check.checked)r.blocked_choices.push(current);sync();});
          checkLabel.append(check,document.createTextNode('Blocked対象')); box.append(checkLabel);
          button(box,'選択肢を削除',()=>{delete r.criteria[current];r.blocked_choices=r.blocked_choices.filter(x=>x!==current);render();builder.children[index].open=true;});
        });
        button(body,'＋ 選択肢',()=>{let i=1;while(Object.hasOwn(r.criteria,'option_'+i))i++;r.criteria['option_'+i]='';render();builder.children[index].open=true;});
      } else {
        r.criteria.forEach((text,i)=>{
          const box=el('div','','option-box');body.append(box);
          field(box, 'レベル '+i,text,v=>r.criteria[i]=v,'textarea');
          button(box,'レベルを削除',()=>{r.criteria.splice(i,1);render();builder.children[index].open=true;});
        });
        button(body,'＋ レベル',()=>{r.criteria.push('');render();builder.children[index].open=true;});
        field(body,'Blocked閾値',r.threshold,v=>r.threshold=v,'number',{min:0,max:Math.max(0,r.criteria.length-1),step:.01});
      }
      button(body,'ルールを削除',()=>{state.splice(index,1);render();});
      builder.append(card);
    });
    document.getElementById('add-rule').disabled=state.length>=10;
    sync();
  }
  document.getElementById('add-rule').addEventListener('click',()=>{
    state.push({id:'rule_'+crypto.randomUUID().replaceAll('-',''),label:'新しいルール',type:'noul',instructions:'',criteria:{true:'',false:''},threshold:.5});render();builder.lastElementChild.open=true;
  });
  document.querySelector('.json-preview').addEventListener('toggle',()=>{if(editor)editor.refresh();});
  render();
  const samples = [...document.querySelectorAll('.sample-button')];
  const updateSelection = () => samples.forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.prompt === prompt.value));
  });
  samples.forEach(button => button.addEventListener('click', () => {
    prompt.value = button.dataset.prompt;
    updateSelection();
  }));
  prompt.addEventListener('input', updateSelection);
  document.getElementById('reset').addEventListener('click', () => {
    state = Object.entries(JSON.parse(initial).rules).map(([id,r])=>({id,...r})); render();
  });
  document.getElementById('guard-form').addEventListener('submit', (e) => {
    if (!window.htmx) {
      e.preventDefault();
      document.getElementById('result').textContent = '画面ライブラリを読み込めませんでした。インターネット接続を確認して再読み込みしてください。';
    }
  });
  document.body.addEventListener('htmx:afterSwap', () => {
    document.querySelectorAll('.configuration').forEach(details => {
      if (details.dataset.ready) return;
      details.dataset.ready = 'true';
      const editors = [];
      details.addEventListener('toggle', () => {
        if (!details.open || !window.CodeMirror) return;
        if (!editors.length) details.querySelectorAll('.raw-json').forEach(textarea => {
          editors.push(CodeMirror.fromTextArea(textarea, {
            mode: {name: 'javascript', json: true}, lineNumbers: true,
            lineWrapping: true, readOnly: true
          }));
        });
        editors.forEach(cm => cm.refresh());
      });
    });
  });
  document.body.addEventListener('htmx:beforeRequest', () => {
    document.getElementById('result').textContent = '判定中…';
  });
  ['htmx:sendError', 'htmx:responseError', 'htmx:timeout'].forEach(event => {
    document.body.addEventListener(event, () => {
      document.getElementById('result').textContent = 'アプリとの通信に失敗しました。接続を確認して再実行してください。';
    });
  });
});

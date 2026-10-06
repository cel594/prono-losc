let rewardTimer = null;
let rewardSequenceActive = false;

function openModal(id){
  const el = document.getElementById(id);
  if (el) el.classList.add('show');
}

function closeModal(id){
  const el = document.getElementById(id);
  if (el) el.classList.remove('show');
}

function closeRewardModal(){
  if (rewardTimer) {
    clearTimeout(rewardTimer);
    rewardTimer = null;
  }
  rewardSequenceActive = false;
  closeModal('rewardModal');
}

function switchAuth(mode){
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab')[mode==='login'?0:1].classList.add('active');
  document.getElementById('loginForm').classList.toggle('hidden',mode!=='login');
  document.getElementById('registerForm').classList.toggle('hidden',mode!=='register');
}

function stepScore(btn,delta){
  const input=btn.parentElement.querySelector('input');
  input.value=Math.max(0,(parseInt(input.value)||0)+delta)
}

async function savePrediction(id,button){
  const card=document.querySelector(`[data-match="${id}"]`);
  const fd=new FormData();
  fd.append('match_id',id);
  fd.append('home_score',card.querySelector('.home-score').value);
  fd.append('away_score',card.querySelector('.away-score').value);
  const r=await fetch('/predict',{method:'POST',body:fd});
  const data=await r.json();
  if(data.ok){
    button.textContent='✓ Prono enregistré';
    button.classList.add('saved');
  }else alert(data.error||'Erreur');
}

async function checkRewards(){
  try{
    const r=await fetch('/api/rewards');
    const data=await r.json();
    if(!data.rewards.length)return;
    openRewardSequence(data.rewards);
  }catch(e){}
}

function openRewardSequence(rewards){
  const modal=document.getElementById('rewardModal');
  const card=modal.querySelector('.reward-card');
  const title=document.getElementById('rewardTitle');
  const text=document.getElementById('rewardText');
  const list=document.getElementById('rewardList');
  const icon=document.getElementById('rewardIcon');
  let i=0;
  rewardSequenceActive = true;

  function show(){
    if (!rewardSequenceActive) return;
    const x=rewards[i];
    card.classList.toggle('exact',!!x.exact);
    icon.textContent=x.exact?'★':'✓';
    title.textContent=x.exact?'SCORE EXACT !':'Bien joué !';
    const packText = x.pack_earned ? ' 🎁 Pack gratuit débloqué !' : '';
    text.innerHTML=`<strong>+${x.points} points</strong> — ${x.match}${packText}`;
    list.innerHTML='';

    if(rewards.length>1){
      rewards.forEach((r)=>{
        const row=document.createElement('div');
        row.className='reward-row';
        row.innerHTML=`<span>${r.match}${r.pack_earned ? ' · 🎁 pack' : ''}</span><b>+${r.points}</b>`;
        list.appendChild(row);
      });
    }
    openModal('rewardModal');

    if(i<rewards.length-1){
      rewardTimer=setTimeout(()=>{
        if(!rewardSequenceActive)return;
        closeModal('rewardModal');
        i++;
        rewardTimer=setTimeout(show,350);
      },2200);
    }
  }
  show();
}

window.addEventListener('load',()=>{
  if(document.body.dataset.logged==='1')checkRewards();
  setTimeout(()=>document.querySelectorAll('.toast').forEach(t=>t.remove()),4500);
});

window.addEventListener('click',(event)=>{
  const modal=event.target.closest('.modal');
  if(modal && event.target===modal){
    if(modal.id==='rewardModal') closeRewardModal();
    else closeModal(modal.id);
  }
});

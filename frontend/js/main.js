/* FleetFlow TMS — App bootstrap & theme */
function toggleTheme(){const r=document.documentElement;const dark=r.dataset.theme?r.dataset.theme==="dark":matchMedia("(prefers-color-scheme: dark)").matches;r.dataset.theme=dark?"light":"dark";render();}
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAll();});

/* Confirm who is signed in, load everything from the database, then draw the first screen */
loadUser().then(refresh).then(render).catch(e=>{$("view").innerHTML=`<div class="card"><b>Cannot reach the API.</b><div class="muted">Start the server with <span class="mono">python app.py</span> and open <span class="mono">http://localhost:8000</span>. (${e.message})</div></div>`;});

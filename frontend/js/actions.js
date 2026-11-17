/* FleetFlow TMS — Actions. Every change is a POST to the API; the UI then re-reads state from the database. */
function rerender(){render();if($("drawer").classList.contains("open")&&S.selLoad&&ld(S.selLoad))openLoad(S.selLoad);}
async function act(path,body,after){
 try{
  const r=await api("POST",path,body);await refresh();
  if(r.toast)toast(r.toast,r.error);
  if(after)after(r);else rerender();
  return r;
 }catch(e){toast(e.message,1);}
}

/* Orders */
function saveOrder(){
 const o=$("nO").value,d=$("nD").value;if(o===d){toast("Origin and destination must differ",1);return;}
 act("api/loads",{cust:$("nCust").value,o,d,pu:$("nPu").value,del:$("nDel").value,equip:$("nEq").value,weight:+$("nW").value,rate:+$("nR").value},()=>{closeAll();render();});
}
const ediImport=()=>act("api/edi/204");

/* Planning & dispatch */
const assign=(lid,did)=>act(`api/loads/${lid}/assign`,{driver:did},()=>{S.selLoad=null;render();});
const unassign=lid=>act(`api/loads/${lid}/unassign`);
const sendMotive=lid=>act(`api/loads/${lid}/dispatch`);

/* Documents & billing */
const attachPod=id=>act(`api/loads/${id}/pod`);
const invoice=id=>act(`api/loads/${id}/invoice`);
const markPaid=id=>act(`api/loads/${id}/pay`);

/* Fleet & integrations */
const mapTruck=id=>act(`api/trucks/${id}/map`);
const retry=id=>act(`api/logs/${id}/retry`);
const resetData=()=>act("api/reset");

/* Driver messaging: the server stores the message and the (simulated) driver replies a few seconds later */
async function sendMsg(id){
 const v=$("msgIn").value.trim();if(!v)return;
 await act(`api/loads/${id}/messages`,{text:v},()=>trkDetail());
 setTimeout(async()=>{
  try{await refresh();}catch(e){return;}
  updateNav();
  if(S.view==="tracking"&&S.selTruck===id)trkDetail();else toast(`New message on ${id}`);
 },3200);
}

/* Live feed: each tick asks the server to advance the telematics simulation, then redraws */
let ticking=false;
async function tick(){
 if(ticking)return;ticking=true;
 try{
  const r=await api("POST","api/simulate/tick");await refresh();
  (r.toasts||[]).forEach(t=>toast(t));
  if(S.view==="tracking")drawMap();else if(S.view!=="orders")rerender();else updateNav();
 }catch(e){toast(e.message,1);}
 finally{ticking=false;}
}

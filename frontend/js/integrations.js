/* FleetFlow TMS — Integrations */
function vInteg(){
 const sys=[["Motive","OBC / ELD telematics","Locations, HOS, dispatch, messages, documents"],["EDI","Customer EDI (VAN)","204 tender · 990 response · 214 status · 210 invoice"],["Accounting","Accounting / ERP","Invoices, payments, driver settlements"],["Payments","Payment gateways","PayPal · Razorpay online invoice payments"],["Mileage","Mileage & routing","Practical miles, routes"]];
 const card=([k,n,desc])=>{const ls=logs.filter(x=>x.sys===k);const er=ls.filter(x=>x.st==="Error").length;return `<div class="card"><h3><span class="pill ${er?"s-Error":"s-Success"}">${er?er+" error"+(er>1?"s":""):"Healthy"}</span>${n}</h3><div class="muted small">${desc}</div><div class="row small" style="margin-top:10px"><span>${ls.length} events</span><span class="muted">Last: ${ls[0]?ls[0].t:"—"}</span></div></div>`;};
 const rows=logs.filter(x=>(S.logSys==="All"||x.sys===S.logSys)&&(S.logSt==="All"||x.st===S.logSt));
 $("view").innerHTML=`
 <div class="grid k4">${sys.map(card).join("")}</div>
 <div class="card" style="margin-top:16px"><h3>Integration event log<span class="sp"></span>
  <select onchange="S.logSys=this.value;render()">${["All","Motive","EDI","Accounting","Payments","Mileage","TMS"].map(s=>`<option ${S.logSys===s?"selected":""}>${s}</option>`).join("")}</select>
  <select onchange="S.logSt=this.value;render()">${["All","Success","Error"].map(s=>`<option ${S.logSt===s?"selected":""}>${s}</option>`).join("")}</select></h3>
  <div class="tw"><table><thead><tr><th>Time</th><th>System</th><th>Dir</th><th>Event</th><th>Ref</th><th>Status</th><th>Detail</th><th></th></tr></thead><tbody>
  ${rows.slice(0,60).map((x)=>{const i=x.id;return `<tr><td class="mono">${x.t}</td><td>${x.sys}</td><td class="mono">${x.dir}</td><td>${x.type}</td><td>${x.ref!=="—"&&ld(x.ref)?`<a href="#" onclick="openLoad('${x.ref}');return false">${x.ref}</a>`:x.ref}</td><td>${pill(x.st)}</td><td class="small">${x.msg}</td><td>${x.st==="Error"?`<button class="btn sm" onclick="retry(${i})">Retry</button>`:""}</td></tr>`;}).join("")}
  </tbody></table></div></div>`;
}

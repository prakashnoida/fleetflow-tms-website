/* FleetFlow TMS — Live tracking */
const US=[[-124.7,48.4],[-123,49],[-95.2,49],[-94.8,49.4],[-89.6,48],[-84.8,46.5],[-82.4,45.3],[-82.5,42.9],[-79,43.3],[-76.3,44.2],[-74.9,45],[-71.5,45],[-69.2,47.4],[-67.8,47.1],[-67,44.8],[-70.6,43.1],[-70,41.8],[-74,40.6],[-75.5,39.4],[-76,37],[-75.5,35.3],[-77.9,33.9],[-81,32],[-81.4,30.4],[-80,26.8],[-80.4,25.2],[-81.8,26.1],[-82.8,27.9],[-84.3,30],[-86.5,30.4],[-89.6,30.2],[-89.4,29],[-91,29.2],[-93.8,29.7],[-95,29.2],[-97.2,27.8],[-97.4,25.9],[-99.5,27.5],[-101.4,29.8],[-103,29],[-104.7,29.9],[-106.5,31.8],[-108.2,31.3],[-111.1,31.3],[-114.8,32.5],[-117.1,32.5],[-118.5,34],[-120.6,34.6],[-121.9,36.6],[-122.5,37.8],[-123.8,39.8],[-124.2,41.9],[-124.1,46.2]];
function vTracking(){
 const tl=loads.filter(active);
 if(!S.selTruck||!tl.find(l=>l.id===S.selTruck))S.selTruck=tl[0]&&tl[0].id;
 $("view").innerHTML=`<div class="grid c2"><div class="card"><h3>Fleet map <span class="sp"></span><span class="muted small">Positions from Motive <span class="mono">/vehicle_locations</span></span></h3><div id="mapW"></div>
  <div class="row small muted" style="margin-top:8px"><span style="color:var(--warn)">● In transit</span><span style="color:var(--accent)">● Dispatched (at shipper)</span><span style="color:var(--err)">● Late</span><span>Tip: turn on "Live OBC feed" to simulate movement.</span></div></div>
  <div class="grid" style="align-content:start"><div class="card"><h3>Active trucks</h3><div class="tw"><table><thead><tr><th>Load</th><th>Driver</th><th>Progress</th><th>ETA</th></tr></thead><tbody id="trkT"></tbody></table></div></div><div class="card" id="trkD"></div></div></div>`;
 drawMap();
}
function drawMap(){
 if(S.view!=="tracking")return;
 const tl=loads.filter(active);
 const poly=US.map(([lo,la])=>proj(la,lo).join(",")).join(" ");
 const cities=Object.entries(CITIES).map(([n,[la,lo]])=>{const[x,y]=proj(la,lo);return `<circle cx="${x}" cy="${y}" r="3" fill="var(--muted)" opacity=".5"/><text x="${x+6}" y="${y-5}" font-size="12" fill="var(--muted)">${n.split(",")[0]}</text>`;}).join("");
 const routes=tl.map(l=>{const[a,b]=proj(...CITIES[l.o]),[c,d]=proj(...CITIES[l.d]);const sel=l.id===S.selTruck;return `<line x1="${a}" y1="${b}" x2="${c}" y2="${d}" stroke="${sel?"var(--accent)":"var(--muted)"}" stroke-width="${sel?3:1.5}" stroke-dasharray="${sel?"":"5 5"}" opacity="${sel?.9:.5}"/>`;}).join("");
 const dots=tl.map(l=>{const[x,y]=proj(...pos(l));const c=l.late?"var(--err)":l.status==="Dispatched"?"var(--accent)":"var(--warn)";const sel=l.id===S.selTruck;return `<g style="cursor:pointer" onclick="selTrk('${l.id}')"><circle cx="${x}" cy="${y}" r="${sel?13:10}" fill="${c}" stroke="var(--panel)" stroke-width="3"/><text x="${x}" y="${y+4}" text-anchor="middle" font-size="10" fill="#fff" font-weight="700">${drv(l.driver).truck.slice(-2)}</text></g>`;}).join("");
 $("mapW").innerHTML=`<svg class="map" viewBox="0 0 1000 560" role="img" aria-label="US fleet map"><polygon points="${poly}" fill="var(--land)" stroke="var(--border)" stroke-width="2"/>${cities}${routes}${dots}</svg>`;
 $("trkT").innerHTML=tl.map(l=>`<tr class="click" onclick="selTrk('${l.id}')" style="${l.id===S.selTruck?"background:var(--accent-soft)":""}"><td><b>${l.id}</b><div class="muted small">${l.o.split(",")[0]} → ${l.d.split(",")[0]}</div></td><td>${drv(l.driver).name}</td><td style="min-width:90px"><div class="bar ${l.late?"err":""}"><i style="width:${l.prog*100}%"></i></div><span class="small muted">${Math.round(l.prog*100)}%</span></td><td>${l.status==="Dispatched"?'<span class="muted small">At shipper</span>':eta(l)}</td></tr>`).join("")||'<tr><td colspan="4" class="muted">No active trucks.</td></tr>';
 trkDetail();
}
function trkDetail(){
 const l=S.selTruck&&ld(S.selTruck);if(!l||!active(l)){$("trkD").innerHTML='<span class="muted">Select a truck.</span>';return;}
 const d=drv(l.driver),t=trk(d.truck);const m=msgs[l.id]||[];const spd=l.status==="In Transit"?58+Math.round(Math.random()*7):0;
 $("trkD").innerHTML=`<h3>${d.truck} · ${d.name}<span class="sp"></span>${pill(l.status)}</h3>
 <dl class="dl"><dt>Load</dt><dd><a href="#" onclick="openLoad('${l.id}');return false">${l.id}</a> · ${l.cust}</dd><dt>Speed</dt><dd>${spd} mph</dd><dt>Last ping</dt><dd>${clock()} <span class="muted small">via Motive Vehicle Gateway ${t.motive||"—"}</span></dd><dt>Fuel</dt><dd>${t.fuel}%</dd>${t.fault?`<dt>Fault code</dt><dd style="color:var(--warn)">${t.fault}</dd>`:""}</dl>
 <h4 style="margin:14px 0 6px;font-size:13px">Hours of Service</h4>
 ${hosBars(d)}
 <h4 style="margin:14px 0 6px;font-size:13px">Driver messages</h4>
 <div class="msgs" id="msgBox">${m.map(x=>`<div class="msg ${x.me?"me":"dr"}">${x.text}<small>${x.t}</small></div>`).join("")||'<span class="muted small">No messages yet.</span>'}</div>
 <div class="row"><input id="msgIn" placeholder="Message driver…" style="flex:1" onkeydown="if(event.key==='Enter')sendMsg('${l.id}')"><button class="btn p" onclick="sendMsg('${l.id}')">Send</button></div>`;
 const mb=$("msgBox");mb.scrollTop=mb.scrollHeight;
}
function hosBars(d){return [["Drive",d.drive,HOS.drive],["Shift",d.shift,HOS.shift],["Cycle",d.cycle,HOS.cycle]].map(([n,v,mx])=>{const p=v/mx;return `<div class="hb"><span class="small">${n}</span><div class="bar ${p<.2?"err":p<.45?"warn":"ok"}"><i style="width:${p*100}%"></i></div><b class="small">${v}h</b></div>`;}).join("");}
function selTrk(id){S.selTruck=id;drawMap();}
function toggleLive(){
 S.live=!S.live;$("liveInd").classList.toggle("on",S.live);$("liveInd").lastChild.textContent=`Live OBC feed: ${S.live?"on":"off"}`;
 if(S.live){S.timer=setInterval(tick,2000);toast("Simulating Motive location pings every 2s");}else clearInterval(S.timer);
}

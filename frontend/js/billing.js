/* FleetFlow TMS — Billing */
function vBilling(){
 const ready=loads.filter(l=>l.status==="Delivered");const inv=loads.filter(l=>l.status==="Invoiced");
 const ar=inv.filter(l=>l.inv.st==="Open").reduce((a,l)=>a+total(l),0);const paid=inv.filter(l=>l.inv.st==="Paid").reduce((a,l)=>a+total(l),0);
 const sett=drivers.map(d=>{const ls=loads.filter(l=>l.driver===d.id&&["Delivered","Invoiced"].includes(l.status));const mi=ls.reduce((a,l)=>a+miles(l),0);return{d,n:ls.length,mi,pay:mi*CPM};}).filter(x=>x.n);
 $("view").innerHTML=`
 <div class="grid k4">${kpi("Ready to invoice",ready.length,money(ready.reduce((a,l)=>a+total(l),0)))}${kpi("Open A/R",money(ar),`${inv.filter(l=>l.inv.st==="Open").length} invoices`)}${kpi("Collected",money(paid),"This period")}${kpi("Driver pay due",money(sett.reduce((a,x)=>a+x.pay,0)),`$${CPM}/mile`)}</div>
 <div class="card" style="margin-top:16px"><h3>Ready to invoice</h3><div class="tw"><table><thead><tr><th>Load</th><th>Customer</th><th>Lane</th><th>Linehaul</th><th>FSC</th><th>Total</th><th>POD</th><th></th></tr></thead><tbody>
  ${ready.map(l=>`<tr><td><a href="#" onclick="openLoad('${l.id}');return false"><b>${l.id}</b></a></td><td>${l.cust}</td><td>${l.o} → ${l.d}</td><td>${money(l.rate)}</td><td>${money(miles(l)*.48)}</td><td><b>${money(total(l))}</b></td><td>${l.pod?'<span class="pill s-Success">Received</span>':'<span class="pill s-Error">Missing</span>'}</td><td>${l.pod?`<button class="btn sm p" onclick="invoice('${l.id}')">Create invoice</button>`:`<button class="btn sm" onclick="openLoad('${l.id}')">Resolve POD</button>`}</td></tr>`).join("")||'<tr><td colspan="8" class="muted">Nothing waiting.</td></tr>'}
 </tbody></table></div></div>
 <div class="grid c2" style="margin-top:16px">
  <div class="card"><h3>Invoices</h3><div class="tw"><table><thead><tr><th>Invoice</th><th>Load</th><th>Customer</th><th>Amount</th><th>Due</th><th>Status</th><th></th></tr></thead><tbody>
   ${inv.map(l=>`<tr><td class="mono">${l.inv.no}</td><td>${l.id}</td><td>${l.cust}</td><td>${money(total(l))}</td><td>${l.inv.due}</td><td>${pill(l.inv.st)}${l.inv.via?` <span class="muted small" title="${l.inv.ref}">via ${l.inv.via==="paypal"?"PayPal":"Razorpay"}</span>`:""}</td><td style="white-space:nowrap">${l.inv.st==="Open"?`<button class="btn sm p" onclick="payOnline('${l.id}')">Pay online</button> <button class="btn sm" onclick="markPaid('${l.id}')">Mark paid</button>`:""}</td></tr>`).join("")}
  </tbody></table></div></div>
  <div class="card"><h3>Driver settlement</h3><table><thead><tr><th>Driver</th><th>Loads</th><th>Miles</th><th>Pay</th></tr></thead><tbody>
   ${sett.map(x=>`<tr><td>${x.d.name}</td><td>${x.n}</td><td>${x.mi.toLocaleString()}</td><td><b>${money(x.pay)}</b></td></tr>`).join("")}
  </tbody></table></div>
 </div>`;
}
const total=l=>l.rate+miles(l)*.48;

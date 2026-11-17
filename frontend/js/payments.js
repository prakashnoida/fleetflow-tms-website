/* FleetFlow TMS — Online invoice payments (PayPal Buttons / Razorpay Checkout).
   The server creates every gateway order for the exact invoice amount and verifies every payment
   with the gateway before it marks the invoice Paid; this file only opens the checkout UIs. */
let PAYCFG=null;
const _scripts={};
function loadScript(src){
 if(!_scripts[src])_scripts[src]=new Promise((ok,fail)=>{const s=document.createElement("script");s.src=src;s.onload=ok;s.onerror=()=>{delete _scripts[src];fail(new Error("Could not load "+src));};document.head.appendChild(s);});
 return _scripts[src];
}
async function payConfig(){if(!PAYCFG)PAYCFG=await api("GET","api/payments/config");return PAYCFG;}
const fmtAmt=(minor,cur)=>{const z=["JPY","KRW","VND","CLP","ISK","HUF","TWD"].includes(cur);return new Intl.NumberFormat("en-US",{style:"currency",currency:cur}).format(z?minor:minor/100);};

async function payOnline(id){
 const l=ld(id);if(!l||!l.inv)return;
 let cfg;try{cfg=await payConfig();}catch(e){toast(e.message,1);return;}
 const amt=Math.round((l.rate+miles(l)*0.48)*cfg.fxRate*100);
 const none=!cfg.paypal.enabled&&!cfg.razorpay.enabled;
 $("modal").innerHTML=`<div class="hd">Pay invoice ${l.inv.no}<span style="flex:1"></span><button class="btn sm" onclick="closeAll()">✕</button></div>
 <div class="bd" style="grid-template-columns:1fr">
  <dl class="dl"><dt>Load</dt><dd>${l.id} · ${l.o} → ${l.d}</dd><dt>Customer</dt><dd>${l.cust}</dd><dt>Amount due</dt><dd><b>${fmtAmt(amt,cfg.currency)}</b>${cfg.currency!=="USD"?` <span class="muted small">(${money(l.rate+miles(l)*0.48)} × ${cfg.fxRate})</span>`:""}</dd></dl>
  ${none?`<div class="note" style="background:var(--warn-soft)">No payment gateway is configured. Copy <span class="mono">.env.example</span> to <span class="mono">.env</span>, add your PayPal and/or Razorpay keys, and restart <span class="mono">python app.py</span>.</div>`:""}
  ${cfg.razorpay.enabled?`<button class="btn p" id="rzpBtn" onclick="payRazorpay('${l.id}')">Pay with Razorpay (cards · UPI · netbanking)</button>`:""}
  ${cfg.paypal.enabled?`<div id="ppBtns" style="min-height:45px"><span class="muted small">Loading PayPal…</span></div>`:""}
  ${cfg.paypal.mode!=="live"&&cfg.paypal.enabled||cfg.razorpay.enabled&&(cfg.razorpay.keyId||"").startsWith("rzp_test")?`<div class="muted small">Test mode: no real money moves. Use sandbox / test credentials.</div>`:""}
  <div id="payMsg" class="small"></div>
 </div>`;
 showModal();
 if(cfg.paypal.enabled)renderPayPal(l.id,cfg);
}

function payStatus(m,err){const el=$("payMsg");if(el){el.textContent=m;el.style.color=err?"var(--err)":"var(--muted)";}}
async function paid(r){await refresh();closeAll();render();toast(r.toast||"Payment received");}

/* PayPal: Smart Payment Buttons. createOrder/onApprove both go through our server. */
async function renderPayPal(id,cfg){
 try{
  await loadScript(`https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(cfg.paypal.clientId)}&currency=${cfg.currency}&intent=capture`);
  const box=$("ppBtns");if(!box)return;box.innerHTML="";
  paypal.Buttons({
   style:{layout:"vertical",shape:"rect",label:"pay"},
   createOrder:async()=>{payStatus("Creating PayPal order…");const r=await api("POST",`api/loads/${id}/checkout`,{provider:"paypal"});payStatus("");return r.orderId;},
   onApprove:async(data)=>{
    payStatus("Confirming payment with PayPal…");
    try{await paid(await api("POST","api/payments/paypal/capture",{orderId:data.orderID}));}
    catch(e){payStatus(e.message,1);toast(e.message,1);}
   },
   onCancel:()=>payStatus("PayPal payment cancelled."),
   onError:e=>{payStatus((e&&e.message)||"PayPal error",1);}
  }).render("#ppBtns");
 }catch(e){const box=$("ppBtns");if(box)box.innerHTML=`<span class="small" style="color:var(--err)">${e.message}</span>`;}
}

/* Razorpay: Standard Checkout popup. The handler's signature is verified on the server. */
async function payRazorpay(id){
 const btn=$("rzpBtn");if(btn)btn.disabled=true;
 try{
  payStatus("Creating Razorpay order…");
  await loadScript("https://checkout.razorpay.com/v1/checkout.js");
  const cfg=await payConfig();
  const o=await api("POST",`api/loads/${id}/checkout`,{provider:"razorpay"});
  payStatus("Complete the payment in the Razorpay window…");
  const rzp=new Razorpay({
   key:cfg.razorpay.keyId,order_id:o.orderId,amount:o.amount,currency:o.currency,
   name:cfg.razorpay.merchant,description:`${o.invoice} · ${o.loadId}`,
   notes:{load_id:o.loadId,invoice:o.invoice},
   prefill:{name:o.customer},theme:{color:getComputedStyle(document.documentElement).getPropertyValue("--accent").trim()||"#2563eb"},
   handler:async resp=>{
    payStatus("Verifying payment…");
    try{await paid(await api("POST","api/payments/razorpay/verify",resp));}
    catch(e){payStatus(e.message,1);toast(e.message,1);}
   },
   modal:{ondismiss:()=>{payStatus("Razorpay checkout closed.");const b=$("rzpBtn");if(b)b.disabled=false;}}
  });
  rzp.on("payment.failed",r=>payStatus(`Payment failed: ${r.error&&r.error.description||"declined"}`,1));
  rzp.open();
 }catch(e){payStatus(e.message,1);toast(e.message,1);const b=$("rzpBtn");if(b)b.disabled=false;}
}

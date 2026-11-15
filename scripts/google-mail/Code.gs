/** CampusFlow mail relay. Paste into a standalone Google Apps Script project. */
function authorizeMail() {
  // Run once in the editor to request only the permission to send mail.
  console.log('Remaining recipient quota: ' + MailApp.getRemainingDailyQuota());
}

function reply_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

function equal_(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function doGet() {
  return reply_({service: 'CampusFlow mail', version: 1});
}

function doPost(e) {
  const properties = PropertiesService.getScriptProperties();
  const secret = properties.getProperty('CAMPUSFLOW_MAIL_SECRET') || '';
  if (secret.length < 32) return reply_({ok:false, code:'UNCONFIGURED'});
  let envelope, message;
  try {
    if (!e || !e.postData || e.postData.contents.length > 32000) throw new Error();
    envelope = JSON.parse(e.postData.contents);
    if (!Number.isInteger(envelope.timestamp) || Math.abs(Date.now()/1000-envelope.timestamp) > 300 || typeof envelope.payload !== 'string') throw new Error();
    const bytes = Utilities.computeHmacSha256Signature(String(envelope.timestamp)+'\n'+envelope.payload, secret, Utilities.Charset.UTF_8);
    const signature = bytes.map(b => ('0'+((b+256)%256).toString(16)).slice(-2)).join('');
    if (!equal_(signature, envelope.signature)) throw new Error();
  } catch (_) {
    return reply_({ok:false, code:'AUTH_FAILED'});
  }
  try {
    message = JSON.parse(envelope.payload);
    if (!/^[a-f0-9]{64}$/.test(message.id) || typeof message.to !== 'string' || message.to.length > 254 || !/^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/.test(message.to) || typeof message.subject !== 'string' || !message.subject || message.subject.length > 300 || /[\r\n]/.test(message.subject) || typeof message.text !== 'string' || message.text.length > 16000) throw new Error();
  } catch (_) {
    return reply_({ok:false, code:'INVALID_MESSAGE'});
  }
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(2000)) return reply_({ok:false, code:'BUSY'});
  try {
    const now = Date.now();
    const key = 'delivery_'+message.id;
    const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, envelope.payload, Utilities.Charset.UTF_8).map(b => ('0'+((b+256)%256).toString(16)).slice(-2)).join('');
    // Bounded retention; no recipient address or body is stored in properties.
    const all = properties.getProperties();
    Object.keys(all).filter(k => k.startsWith('delivery_')).forEach(k => {
      const record = JSON.parse(all[k]);
      if (record.at < now-48*60*60*1000) properties.deleteProperty(k);
    });
    const previous = properties.getProperty(key);
    if (previous) {
      const record = JSON.parse(previous);
      if (record.digest !== digest) return reply_({ok:false, code:'ID_CONFLICT'});
      return record.state === 'sent' ? reply_({ok:true, id:message.id, duplicate:true}) : reply_({ok:false, code:'DELIVERY_UNCERTAIN'});
    }
    if (MailApp.getRemainingDailyQuota() < 1) return reply_({ok:false, code:'QUOTA_EXCEEDED'});
    // Save before sending: after an ambiguous failure do not risk an automatic duplicate.
    properties.setProperty(key, JSON.stringify({at:now, digest:digest, state:'processing'}));
    try {
      MailApp.sendEmail({to:message.to, subject:message.subject, body:message.text, name:'CampusFlow'});
      properties.setProperty(key, JSON.stringify({at:now, digest:digest, state:'sent'}));
      return reply_({ok:true, id:message.id});
    } catch (_) {
      return reply_({ok:false, code:'DELIVERY_UNCERTAIN'});
    }
  } finally {
    lock.releaseLock();
  }
}

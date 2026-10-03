/**
 * Number → English words using Pakistani numbering (crore / lakh / thousand).
 * Used for the wholesale invoice "amount in words" line.
 * numToWordsPKR(1080) → "Rupees One Thousand Eighty Only"
 */
const ONES = [
  'Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
  'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
  'Seventeen', 'Eighteen', 'Nineteen',
];
const TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];

function under100(n) {
  if (n < 20) return ONES[n];
  const t = TENS[Math.floor(n / 10)];
  return n % 10 ? `${t} ${ONES[n % 10]}` : t;
}

function under1000(n) {
  if (n < 100) return under100(n);
  const h = `${ONES[Math.floor(n / 100)]} Hundred`;
  return n % 100 ? `${h} ${under100(n % 100)}` : h;
}

export function numberToWords(n) {
  let v = Math.round(Math.abs(Number(n) || 0));
  if (v === 0) return ONES[0];
  const parts = [];
  const crore = Math.floor(v / 1e7);
  const lakh = Math.floor((v % 1e7) / 1e5);
  const thousand = Math.floor((v % 1e5) / 1e3);
  const rest = v % 1e3;
  if (crore) parts.push(`${under1000(crore)} Crore`);
  if (lakh) parts.push(`${under1000(lakh)} Lakh`);
  if (thousand) parts.push(`${under1000(thousand)} Thousand`);
  if (rest) parts.push(under1000(rest));
  return parts.join(' ');
}

export function numToWordsPKR(n) {
  const v = Number(n) || 0;
  const words = numberToWords(v);
  const paisa = Math.round((Math.abs(v) % 1) * 100);
  const paisaStr = paisa > 0 ? ` and Paise ${numberToWords(paisa)}` : '';
  return `Rupees ${words}${paisaStr} Only`;
}

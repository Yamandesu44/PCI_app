/**
 * 免責とデータの出どころを常設で示す。
 *
 * 馬券に隣接するサービスとして、**的中や利益を保証しないこと**と
 * **推奨ではないこと**は、個別の画面ではなくサイト全体で一度述べておく必要がある。
 * 個人ツールだった頃は誰も読まないので省いていたが、公開した以上は
 * 「読んだ人がどう受け取るか」の責任がこちら側にある。
 *
 * 併せてデータの出どころと更新の頻度を書く。古い情報を見ている可能性が
 * あることを、障害時のバナーだけに頼らず伝えるため。
 */
export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-slate-200 bg-slate-50">
      <div className="mx-auto w-full max-w-7xl px-4 py-8 md:px-6 lg:px-8">
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <p className="m-0 text-sm font-semibold text-slate-800">PACE LAB</p>
            <p className="m-0 mt-2 text-xs leading-6 text-slate-600">
              レースの展開（速さの流れ）を予測し、その流れで持ち味を出しやすい馬を示します。
              指数の知識がなくても読める形にすることを目的にしています。
            </p>
          </div>
          <div>
            <p className="m-0 text-sm font-semibold text-slate-800">ご利用にあたって</p>
            <ul className="m-0 mt-2 list-disc space-y-1.5 pl-4 text-xs leading-6 text-slate-600">
              <li>
                <strong className="font-semibold text-slate-700">
                  的中・利益を保証するものではありません。
                </strong>
                表示内容は分析結果であり、馬券の購入を推奨するものではありません。
              </li>
              <li>馬券の購入は、ご自身の判断と責任でお願いします。</li>
              <li>
                競馬データを元に独自に算出した指標・予想を表示しています。
                取り込みの遅れにより、最新でない情報が表示される場合があります。
              </li>
              <li>20歳未満の方は馬券を購入できません。</li>
            </ul>
          </div>
        </div>
        <p className="m-0 mt-6 border-t border-slate-200 pt-4 text-[11px] text-slate-500">
          本サイトは JRA および JRA-VAN とは関係のない個人開発のサービスです。
        </p>
      </div>
    </footer>
  );
}

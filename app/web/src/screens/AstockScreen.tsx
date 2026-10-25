import { StockTab } from '../tabs/StockTab';
import { ResearchTab } from '../tabs/ResearchTab';
import { LimitUpTab } from '../tabs/LimitUpTab';
import { ReviewTab } from '../tabs/ReviewTab';
import { InspectionTab } from '../tabs/InspectionTab';
import { OptimizationTab } from '../tabs/OptimizationTab';
import { MasteryTab } from '../tabs/MasteryTab';

// A股投研：长页面，集中承载全部交易类功能（复用现有 7 个 A股 tab 组件为分区，带锚点）。
// 各组件自带后端数据接线（东方财富 provider），此处仅做布局归组，不重复_fetch。
const SECTIONS: { id: string; Comp: () => JSX.Element }[] = [
  { id: 'sec-market', Comp: StockTab },
  { id: 'sec-grade', Comp: ResearchTab },
  { id: 'sec-board', Comp: LimitUpTab },
  { id: 'sec-recap', Comp: ReviewTab },
  { id: 'sec-inspect', Comp: InspectionTab },
  { id: 'sec-optimize', Comp: OptimizationTab },
  { id: 'sec-mastery', Comp: MasteryTab },
];

export function AstockScreen() {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>A股投研</h1>
      <p className="zw-muted" style={{ marginBottom: 24 }}>
        长页面：集中承载全部交易类功能（示例/真实数据）
      </p>
      {SECTIONS.map(({ id, Comp }) => (
        <section key={id} id={id} style={{ scrollMarginTop: 32, marginBottom: 24 }}>
          <Comp />
        </section>
      ))}
    </div>
  );
}

import { SectionCard } from '../components/SectionCard';
import { StockTab } from '../tabs/StockTab';
import { ResearchTab } from '../tabs/ResearchTab';
import { LimitUpTab } from '../tabs/LimitUpTab';
import { ReviewTab } from '../tabs/ReviewTab';
import { InspectionTab } from '../tabs/InspectionTab';
import { OptimizationTab } from '../tabs/OptimizationTab';
import { MasteryTab } from '../tabs/MasteryTab';

// A股投研：长页面，集中承载全部交易类功能（复用现有 7 个 A股 tab 组件为分区大卡片）。
// 每个分区为大卡片，点击卡片标题可折叠/展开内容；各组件自带后端数据接线，此处仅做布局归组。
const SECTIONS: { id: string; title: string; Comp: () => JSX.Element }[] = [
  { id: 'sec-market', title: '行情总览', Comp: StockTab },
  { id: 'sec-grade', title: '个股分级研究', Comp: ResearchTab },
  { id: 'sec-board', title: '超短连板 / 题材 / 情绪', Comp: LimitUpTab },
  { id: 'sec-recap', title: '大V自动复盘', Comp: ReviewTab },
  { id: 'sec-inspect', title: '持仓AI巡检', Comp: InspectionTab },
  { id: 'sec-optimize', title: 'AI持仓优化', Comp: OptimizationTab },
  { id: 'sec-mastery', title: '游资心法与 AI Copilot', Comp: MasteryTab },
];

export function AstockScreen() {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>A股投研</h1>
      <p className="zw-muted" style={{ marginBottom: 24 }}>
        长页面：集中承载全部交易类功能（示例/真实数据）。点击卡片标题可折叠 / 展开对应分区。
      </p>
      {SECTIONS.map(({ id, title, Comp }) => (
        <SectionCard key={id} id={id} title={title}>
          <Comp />
        </SectionCard>
      ))}
    </div>
  );
}

import { NavLink, Outlet } from "react-router-dom";

const items = [
  { to: "/", label: "프로젝트", end: true },
  { to: "/library", label: "지식 DB" },
  { to: "/criteria", label: "내 판단 기준" },
  { to: "/goldens", label: "골든 라이브러리" },
];
const link = ({ isActive }: { isActive: boolean }) =>
  `block rounded-xl px-3 py-2 text-sm ${isActive ? "bg-accent-soft font-bold text-accent" : "text-ink-2 hover:bg-paper"}`;

export default function Layout() {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-[15rem_minmax(0,1fr)]">
      <nav aria-label="메뉴" className="border-b border-rule bg-white p-3 md:sticky md:top-0 md:h-screen md:border-r md:border-b-0 md:p-4">
        <div className="mb-4 hidden items-center gap-2.5 px-2 md:flex">
          <span className="grid size-8 place-items-center rounded-xl bg-accent text-sm font-extrabold text-white">MI</span>
          <div><b className="block text-sm">Market Intelligence</b><span className="text-[11px] text-muted">리서치하고 판단 기준을 다듬는 작업실</span></div>
        </div>
        <NavLink to="/projects/new" className="btn-primary mb-3 w-full">+ 새 프로젝트</NavLink>
        <div className="flex flex-wrap gap-1 md:block md:space-y-0.5">
          {items.map((i) => <NavLink key={i.to} to={i.to} end={i.end} className={link}>{i.label}</NavLink>)}
          <div className="hidden px-3 pt-4 pb-1 text-xs text-muted md:block">개발자</div>
          <NavLink to="/dev" className={link}>개발자 평가</NavLink>
        </div>
      </nav>
      <main className="mx-auto w-full min-w-0 max-w-6xl px-4 py-6 md:px-8 md:py-8"><Outlet /></main>
    </div>
  );
}

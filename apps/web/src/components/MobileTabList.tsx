"use client";

import type { KeyboardEvent } from "react";
import type { LucideIcon } from "lucide-react";

export interface MobileTabOption<T extends string> {
  id: T;
  label: string;
  icon: LucideIcon;
}

interface MobileTabListProps<T extends string> {
  tabs: readonly MobileTabOption<T>[];
  activeTab: T;
  onTabChange: (tab: T) => void;
  ariaLabel: string;
  tabIdPrefix: string;
  panelIdPrefix: string;
  columnsClassName: string;
}

export function tabIndexForKey(
  currentIndex: number,
  key: string,
  tabCount: number,
): number | null {
  if (tabCount <= 0) return null;
  if (key === "ArrowRight") return (currentIndex + 1) % tabCount;
  if (key === "ArrowLeft") return (currentIndex - 1 + tabCount) % tabCount;
  if (key === "Home") return 0;
  if (key === "End") return tabCount - 1;
  return null;
}

export function MobileTabList<T extends string>({
  tabs,
  activeTab,
  onTabChange,
  ariaLabel,
  tabIdPrefix,
  panelIdPrefix,
  columnsClassName,
}: MobileTabListProps<T>) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
    const nextIndex = tabIndexForKey(currentIndex, event.key, tabs.length);
    if (nextIndex === null) return;

    event.preventDefault();
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;

    onTabChange(nextTab.id);
    const tabButtons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
      '[role="tab"]',
    );
    tabButtons?.[nextIndex]?.focus();
  };

  return (
    <>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className={`grid h-12 ${columnsClassName} overflow-hidden rounded-md border border-slate-200 bg-slate-50`}
      >
        {tabs.map((tab, index) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`${tabIdPrefix}-${tab.id}`}
              type="button"
              role="tab"
              tabIndex={isActive ? 0 : -1}
              aria-selected={isActive}
              aria-controls={`${panelIdPrefix}-${tab.id}`}
              onClick={() => onTabChange(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`flex min-w-0 flex-col items-center justify-center gap-0.5 border-r border-slate-200 text-[11px] font-semibold last:border-r-0 ${
                isActive ? "bg-slate-950 text-white" : "bg-white text-slate-500"
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {tab.label}
            </button>
          );
        })}
      </div>

      {tabs
        .filter((tab) => tab.id !== activeTab)
        .map((tab) => (
          <div
            key={`${tab.id}-panel-placeholder`}
            id={`${panelIdPrefix}-${tab.id}`}
            role="tabpanel"
            aria-labelledby={`${tabIdPrefix}-${tab.id}`}
            hidden
          />
        ))}
    </>
  );
}

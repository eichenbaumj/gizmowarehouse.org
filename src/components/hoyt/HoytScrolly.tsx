// Sticky-stage scrolly section. Children are <hs-step> cards; the most-visible card drives the stage.
// Desktop: stage left (3fr) sticky at 100vh, cards right (2fr). Mobile: stage sticky at 60vh on top,
// cards scroll beneath. Reduced motion is provided to the stage through context.
import { Children, createContext, isValidElement, useContext, useMemo, useRef, type CSSProperties, type ReactNode } from "react";
import { useInViewStep } from "@/hooks/useInViewStep";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { MOBILE_STAGE_VH } from "@/config/hoytSchermerhorn";
import MountWhenNear from "@/components/MountWhenNear";
import { HoytCityGrid } from "./HoytCityGrid";

export interface StageContextValue { activeIndex: number; activeStep: string; steps: string[]; reducedMotion: boolean }
export const StageContext = createContext<StageContextValue>({ activeIndex: 0, activeStep: "", steps: [], reducedMotion: false });

function stepIds(children: ReactNode): string[] {
  const ids: string[] = [];
  Children.forEach(children, (c) => {
    if (isValidElement(c) && (c.props as any)?.step) ids.push(String((c.props as any).step));
  });
  return ids;
}

export function HoytScrolly({ stage = "city", id, children }: { stage?: "city"; id?: string; children?: ReactNode }) {
  const steps = useMemo(() => stepIds(children), [children]);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);
  const idx = useInViewStep(stepRefs, { rootMargin: "-40% 0px -40% 0px" });
  const activeIndex = idx < 0 ? 0 : idx;
  const reducedMotion = usePrefersReducedMotion();
  const ctx: StageContextValue = { activeIndex, activeStep: steps[activeIndex] ?? steps[0] ?? "", steps, reducedMotion };
  let i = 0;
  const cards = Children.map(children, (c) => {
    if (!isValidElement(c) || !(c.props as any)?.step) return c;
    const k = i++;
    return (
      <div key={k} ref={(el) => { stepRefs.current[k] = el; }} className="flex min-h-[55vh] items-center py-6 md:min-h-[60vh]" data-step={(c.props as any).step}>
        {c}
      </div>
    );
  });
  return (
    <StageContext.Provider value={ctx}>
      <section id={id} className="not-prose relative my-10" style={{ width: "min(100vw - 1.5rem, 100rem)", marginLeft: "calc(50% - min(100vw - 1.5rem, 100rem) / 2)" }}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)] md:gap-6">
          <div className="sticky top-6 z-[1] h-[var(--stage-h)] self-start md:h-[calc(100vh-3rem)]" style={{ "--stage-h": `${MOBILE_STAGE_VH}vh` } as CSSProperties}>
            <div className="relative h-full w-full overflow-hidden rounded-xl bg-vellum md:h-full">
              <MountWhenNear placeholderHeight="100%">
                {stage === "city" ? <HoytCityGrid /> : null}
              </MountWhenNear>
            </div>
          </div>
          <div className="px-1 md:px-0">{cards}</div>
        </div>
      </section>
    </StageContext.Provider>
  );
}

export function HoytStep({ step, children }: { step: string; children?: ReactNode }) {
  const { activeStep, steps } = useContext(StageContext);
  const active = activeStep === step;
  const n = steps.indexOf(step) + 1;
  return (
    <div className={`w-full rounded-2xl border bg-white/95 px-6 py-6 shadow-[0_8px_30px_rgba(0,0,0,0.10)] backdrop-blur transition-all duration-500 sm:px-8 sm:py-7 ${active ? "border-cobalt/40 opacity-100 translate-y-0" : "border-slate-200 opacity-60 translate-y-1"}`}>
      {steps.length > 1 && <div className="mb-3 flex items-center gap-2 font-sans text-[11px] font-semibold uppercase tracking-[0.12em] text-steel"><span className="inline-block h-[2px] w-6 bg-cobalt" />{n} of {steps.length}</div>}
      <div className="prose prose-slate max-w-none font-serif text-[1.125rem] leading-[1.6] text-charcoal md:text-[1.25rem] [&_p]:my-0 [&_p+p]:mt-5 [&_b]:text-cobalt [&_strong]:text-cobalt">{children}</div>
    </div>
  );
}

export function useStage() {
  return useContext(StageContext);
}

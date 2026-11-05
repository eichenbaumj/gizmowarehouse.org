// Live registry for the hs-* tags. Spread into src/content/embeds.tsx at publish; until then consumed
// only by src/dev/drafts.tsx (localhost). Tag names are lowercase and must not collide with HTML.
import type { ComponentType } from "react";
import { HoytScrolly, HoytStep } from "./HoytScrolly";
import { HoytCityExplore } from "./HoytCityGrid";
import { HoytDraft, HoytDownloads } from "./HoytChrome";
import { HoytPhoto } from "./HoytPhoto";
import { HoytRibbon } from "./HoytRibbon";
import { HoytTimelapse } from "./HoytTimelapse";
import { HoytHourBars, HoytLines, HoytSankey } from "./HoytCharts";
import { HoytPrecinctStrip } from "./HoytPrecincts";
import { HoytPrecinctMap } from "./HoytPrecinctMap";
import { HoytRateMap } from "./HoytRateMap";
import { HoytSiteMap } from "./HoytSiteMap";
import { HoytWeekCompare } from "./HoytStrips";
import { HoytLedgerCard, HoytMethodsNote, HoytRankLadder } from "./HoytCards";

export const hoytEmbeds: Record<string, ComponentType<any>> = {
  "hs-scrolly": HoytScrolly,
  "hs-step": HoytStep,
  "hs-draft": HoytDraft,
  "hs-photo": HoytPhoto,
  "hs-city-explore": HoytCityExplore,
  "hs-timelapse": HoytTimelapse,
  "hs-hour-bars": HoytHourBars,
  "hs-week": HoytWeekCompare,
  "hs-precinct-strip": HoytPrecinctStrip,
  "hs-precinct-map": HoytPrecinctMap,
  "hs-rate-map": HoytRateMap,
  "hs-site-map": HoytSiteMap,
  "hs-sankey": HoytSankey,
  "hs-lines": HoytLines,
  "hs-ribbon": HoytRibbon,
  "hs-ledger": HoytLedgerCard,
  "hs-rank-ladder": HoytRankLadder,
  "hs-methods-note": HoytMethodsNote,
  "hs-downloads": HoytDownloads,
};

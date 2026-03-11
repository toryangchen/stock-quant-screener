export type TrendPoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type StockTrend = {
  code: string;
  name: string;
  points: TrendPoint[];
};

export type PickedStock = {
  code: string;
  name: string;
  is_secondary: boolean;
  entry_price: number;
  latest_price: number;
  return_pct: number;
  pct_chg: number;
  ret_20_stock: number;
  vol_ratio: number;
  vol_score: number;
  risk_pct: number;
  stop_price: number;
  ma10_price: number;
  ma20_price: number;
  score: number;
  suggested_shares: number;
  suggested_position_value: number;
  mkt_cap: number;
};

export type ScreeningResponse = {
  date: string;
  today: string;
  stocks: PickedStock[];
  primary_stocks: PickedStock[];
  secondary_stocks: PickedStock[];
  trends: StockTrend[];
};

export type EtfPick = {
  code: string;
  name: string;
  rank: number;
  ret_pct: number;
  above_ma: boolean;
  ma_price: number;
  close: number;
  decision: string;
};

export type EtfResponse = {
  date: string;
  decision: string;
  etfs: EtfPick[];
};

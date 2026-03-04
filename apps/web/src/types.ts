export type TrendPoint = {
  date: string;
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
  entry_price: number;
  latest_price: number;
  return_pct: number;
};

export type ScreeningResponse = {
  date: string;
  today: string;
  stocks: PickedStock[];
  trends: StockTrend[];
};

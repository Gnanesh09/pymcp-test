declare global {
  interface Window {
    Razorpay?: new (options: any) => {
      open: () => void;
    };
  }
}

export type Product = {
  id: string;
  name: string;
  brand: string;
  category: string;
  price_paise: number;
  price: number;
  mrp_paise: number;
  rating: number;
  stock: number;
  unit: string;
  description: string;
  image: string;
};

export {};

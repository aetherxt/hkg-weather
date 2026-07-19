import { WeatherDashboard } from "@/components/weather-dashboard";
import { loadInitialWeatherForPage } from "@/lib/weather/server";

export default async function Home() {
  const initialWeather = await loadInitialWeatherForPage();
  return <WeatherDashboard initialWeather={initialWeather} />;
}

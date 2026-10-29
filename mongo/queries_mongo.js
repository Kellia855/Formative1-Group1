// MongoDB queries - run in Compass's MONGOSH panel or in mongosh.
// Each query is separate: paste and run them one at a time.
use("electricity_db");

// Q1: Average consumption and production per month
db.energy_records.aggregate([
  { $group: {
      _id: { $dateToString: { format: "%Y-%m", date: "$timestamp" } },
      avg_consumption: { $avg: "$consumption" },
      avg_production:  { $avg: "$production" } } },
  { $project: { _id: 0, year_month: "$_id",
      avg_consumption: { $round: ["$avg_consumption", 2] },
      avg_production:  { $round: ["$avg_production", 2] } } },
  { $sort: { year_month: 1 } }
]);

// Q2: The 5 hours with the highest consumption
db.energy_records.find(
  {},
  { _id: 0, timestamp: 1, consumption: 1, production: 1 }
).sort({ consumption: -1 }).limit(5);

// Q3: Renewable share of total generation per year
// (renewable = wind + hydroelectric + solar + biomass)
db.energy_records.aggregate([
  { $group: {
      _id: { $year: "$timestamp" },
      renewable: { $sum: { $add: ["$generation.wind", "$generation.hydroelectric",
                                  "$generation.solar", "$generation.biomass"] } },
      total: { $sum: { $add: ["$generation.nuclear", "$generation.wind",
                              "$generation.hydroelectric", "$generation.oil_and_gas",
                              "$generation.coal", "$generation.solar",
                              "$generation.biomass"] } } } },
  { $project: { _id: 0, year: "$_id",
      renewable_share_pct: { $round: [{ $multiply: [{ $divide: ["$renewable", "$total"] }, 100] }, 2] } } },
  { $sort: { year: 1 } }
]);

// Q4: Records in a date range (the same filter the API's date-range endpoint will use)
db.energy_records.find(
  { timestamp: { $gte: ISODate("2023-01-01T00:00:00Z"), $lt: ISODate("2023-01-02T00:00:00Z") } },
  { _id: 0 }
).sort({ timestamp: 1 });

// Q5: Average consumption by hour of day
db.energy_records.aggregate([
  { $group: { _id: { $hour: "$timestamp" }, avg_consumption: { $avg: "$consumption" } } },
  { $project: { _id: 0, hour_of_day: "$_id", avg_consumption: { $round: ["$avg_consumption", 2] } } },
  { $sort: { hour_of_day: 1 } }
]);
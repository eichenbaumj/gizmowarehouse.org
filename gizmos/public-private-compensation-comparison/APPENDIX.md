# Technical Appendix — The Public-Sector Pay Gap

This appendix documents every data source, modeling choice, and limitation behind
the charts. The piece is built to read without it; this is for the reader who wants
to check the work. All figures are reproducible from the staged pipeline in the
gizmo's source folder.

## Data sources

**Public-versus-private wages (the engine).** [Census ACS PUMS](https://www.census.gov/programs-surveys/acs/microdata.html)
1-year microdata, pulled per state for 2005, 2010, 2015, 2019, and 2023 via the
Census microdata API. Each person record carries a *class-of-worker* code that
separates federal, state, and local government from private for-profit, private
nonprofit, and the self-employed. That is the clean lever for "public versus
private," which NAICS industry codes do not provide; they would file a government
software engineer under "professional services." We also use occupation (SOC), wage
and salary income, usual hours, weeks worked, education, age, sex, race, and state.
There is no standard 1-year ACS for 2020 (pandemic data collection failure), so it
is skipped.

**Compensation growth over time.** The [BLS Employment Cost Index](https://www.bls.gov/eci/)
(ECI) provides fixed-weight indexes of private and state-and-local compensation and
wages from 2001, used for the "total comp versus wages" panel. Benefit-share levels
are from the [BLS Employer Costs for Employee Compensation](https://www.bls.gov/ncs/)
survey. The federal compensation line uses [BEA national accounts](https://www.bea.gov/).

**Workforce headcounts.** [BLS Current Employment Statistics](https://www.bls.gov/ces/)
government supersectors (federal, state, local; 1939 to present) for the trend and
the government share of employment; the [Census Annual Survey of Public Employment &
Payroll](https://www.census.gov/programs-surveys/apes.html) for full-time-equivalent
counts and payroll by government type. Census stopped publishing federal employment
in that survey after 2014, so the federal headcount is from CES. The public-school
teacher count (about 3.25 million) is from [NCES Common Core of Data](https://nces.ed.gov/)
(2023-24); education is roughly half of local-government employment. The on-page stat strip
and the Sankey, however, are drawn from ACS (employed residents aged 25 to 64) so they line up
with each other and with the wage charts; CES (~23M government jobs, ~15% of employment) and
NCES (3.25M K-12 classroom teachers) are the standard comparisons cited in the chart footnotes.

**City pay.** Each city's own published payroll file: New York ([NYC Open Data](https://data.cityofnewyork.us/City-Government/Citywide-Payroll-Data-Fiscal-Year-/k397-673e)),
Chicago, San Francisco, Seattle, and Los Angeles, pulled via their Socrata APIs and
filtered to full-time salaried employees.

**Education-gradient anchor.** The [Congressional Budget Office's 2024 comparison of
federal and private compensation](https://www.cbo.gov/publication/60235), which
measures total compensation (wages plus benefits) and is the nonpartisan benchmark
for the finding that the federal advantage reverses at the advanced-degree tail.

**Younger workers.** Evidence on the age structure of public employment and the
value of back-loaded pensions draws on [Pew](https://www.pewresearch.org/), the
[Partnership for Public Service](https://ourpublicservice.org/),
[MissionSquare Research Institute (2024)](https://www.missionsq.org/), and
[Costrell and Podgursky](https://www.tiaa.org/).

## How the gap is estimated

**Wage definition.** Real wage is annual wage-and-salary income (or that figure
divided by hours and weeks for an hourly measure), deflated to constant 2026 dollars
with the CPI-U taken to the latest available month. The level series restricts to
full-time workers aged 25 to 64 with positive wages, the standard human-capital
sample used by CBO, EPI, and Biggs and Richwine. Estimates are weighted by the ACS
person weight.

**Weighted percentiles.** Quantiles are weighted by the ACS person weight and
computed with linear interpolation (the Hazen plotting position, the standard choice
for survey weights). ACS reports wages in rounded amounts, so a median can still land
on a common round-number salary that the survey cannot resolve any finer; this is why,
in a few fields, the public and private medians coincide almost to the dollar even
though the distributions diverge above the median. Read small median differences as
approximate and weight the top-of-field (90th-percentile) comparison, which is far more
separated.

**Teachers.** Public education is roughly half of local-government employment, and
teachers have no clean private-sector comparator, so the macro charts can exclude the
education-instruction occupation group (SOC 25) from the government line.

**Workforce mix.** The Sankey on the landing chart is built from ACS PUMS (employed
residents aged 25 to 64, including active-duty military), grouped on a finer
SOC-to-workgroup crosswalk than the wage domains so the residual "Other" share is
negligible. Active-duty military is the full uniformed force aged 25 to 64 (~0.85M),
identified by armed-forces employment status rather than occupation code, so members in
medical, legal, or trade roles count as military rather than scattering into those
buckets; the full active-duty force is about 1.3M counting all ages (DoD), since it
skews young. Its level totals differ from the BLS CES headcounts in the stat strip
because the two measure different universes: CES counts payroll jobs of all ages,
civilian only, while ACS counts employed people 25 to 64 by occupation and includes the
military. The chart is read for the occupation mix, not the totals.

The two teacher figures reconcile the same way. The stat strip's 3.25M is the NCES count
of K-12 classroom teachers; the Sankey's "Teachers & instructors" (~5.5M) is the full SOC
25 occupation group, which adds public-college faculty, special-education teachers,
librarians, and teaching assistants, and spans federal, state, and local. Narrow the ACS
to local K-12 classroom teachers and it lands near 3.2M, in line with NCES.

**Knowledge-economy ladder.** The "knowledge economy" toggle on the wage-ladder chart
restricts both the private percentiles and the government median to the knowledge-economy
domains (software, legal, finance, engineering, management), where the private top has
pulled away hardest.

**Raw, adjusted, and top of the field.** The raw gap is the difference in weighted
medians. The adjusted gap is a weighted least-squares (Mincer) regression of log real
wage on education, an age (experience) quadratic, hours, sex, race, and state fixed
effects, with indicators for each government level; the coefficient, transformed as
exp(beta) minus 1, is the composition-adjusted gap versus private-for-profit, with
heteroskedasticity-robust standard errors. We report it with a sensitivity range
across three specifications (full, dropping education, dropping geography), because
that choice is what divides the published literature ([Biggs and Richwine](https://www.aei.org/)
versus [Allegretto and Mishel / EPI](https://www.epi.org/); see
[GAO-12-564](https://www.gao.gov/products/gao-12-564)). The top-of-field gap compares
the 90th percentile of each side, where the elite private firms pay. Census top-codes
the highest earners, so it is a floor.

**The compression curve.** The education chart plots that same composition-adjusted
wage gap *within* each education bucket (less-than-high-school through doctorate),
computed separately for federal, state, and local. Every government line begins at or
above the private market for less-educated workers and slopes below it as credentials
rise — a higher floor and a lower ceiling. The shape is robust and matches the
[CBO (2024)](https://www.cbo.gov/publication/60235) total-compensation gradient
(+40% at high-school-or-less, roughly even at a bachelor's, −22% at the doctoral/
professional level). Two cautions belong on it. First, the slope is steepest and
best-established for the **federal** government; the **state and local** level is
smaller and genuinely contested — wage-based estimates range from a modest premium
([Gittleman & Pierce, JEP 2012](https://www.aeaweb.org/articles?id=10.1257/jep.26.1.217))
to a single-digit penalty (EPI/Keefe), depending on how defined-benefit pensions and
retiree health are valued — and the low-end federal premium is itself driven more by
benefits than by salary (on wages alone, federal pay runs modestly below private
overall). Second, the reading that unionization helps hold the floor up is an
*inference*: public-sector union density (about 33% versus 6% private,
[BLS](https://www.bls.gov/news.release/union2.nr0.htm)) is concentrated in uniformed
and frontline occupations rather than in government's professional roles, and unions
are known to compress the wage distribution ([Card 2001](https://davidcard.berkeley.edu/papers/union-wage-ineq.pdf)),
but there is no single published "within-government, by-skill" union-premium statistic;
the gradient is assembled from occupation-group rates.

**Why fed, state, and local stay separate.** The adjusted gaps have opposite signs by
level of government (federal modestly positive, state and local negative), so a single
"public sector" coefficient averages away the structure.

**Occupation to domain.** Detailed SOC occupation codes are rolled into analyst-
friendly domains via a versioned crosswalk shipped with the source, mapped at the SOC
major/minor-group level, which is stable across the 2000, 2010, and 2018 SOC vintages.

**Cities.** City-government pay is full-time salaried base pay from each city's
payroll file (NYC, Chicago, San Francisco, Seattle, Los Angeles), deflated to 2026
dollars. Free-text civil-service titles are mapped to domains with an ordered keyword
classifier (versioned in the source). The private comparator is the private sector in
that city's **metro** — the central county or counties (e.g. the five boroughs for
New York, San Francisco County for San Francisco, Cook County for Chicago) — computed
from ACS PUMS for the PUMAs in that metro, full-time/full-year, at the median and the
90th percentile. The city-to-PUMA crosswalk is built from the Census 2020 tract-to-
PUMA relationship file and shipped with the source. The two sides are quantiled
differently by necessity: the city figures are unweighted empirical medians and
90th percentiles of the individual payroll records (a payroll file is a census of
employees, so it carries no survey weights), while the metro-private comparator is
weighted by the ACS person weight, as elsewhere in the piece.

## Known limitations

- **Wages are not total compensation.** Public benefits and pensions are relatively
  richer, so a wages-only comparison overstates the public deficit at lower education
  and understates it at the top. The CBO total-compensation gradient is the better
  anchor for the elite-lag claim, and it still goes negative for advanced degrees. The
  mirror also holds at the top: a large, rising share of elite private pay is bonus,
  stock, and carried interest, which the public sector essentially lacks and which the
  wage figures here (and the BLS ECEC compensation concept) do not capture as equity —
  so the measured top-of-field gap is a floor on that count too.
- **Roles government does not staff.** Some of the highest-paying private occupations —
  product and platform engineering, elite data science — barely exist as government job
  classifications (the federal "data scientist" series dates only to 2021), so they
  never enter the comparison. That truncation biases the measured public-private gap
  downward by an amount these data cannot quantify; we flag it as directional, not a
  number.
- **No public-versus-private split at the very top.** The top 1% of wages cannot be
  measured from survey microdata, and the tax-based series that reach the top carry no
  sector field. Any top-1% figure here is economy-wide.
- **Occupation is not perfectly harmonized over time.** We map to broad domains rather
  than chase fine detail across two decades.
- **Adjustment does not control for within-domain job mix.** The regression holds
  education, age, hours, and geography equal, but not the mix of occupations inside a
  domain. Protective service is the clearest case: the public side is sworn police and
  firefighters while the private comparator is mostly security guards, so its large
  adjusted public premium is largely a difference in jobs, not pay for the same job. The
  selected-domain note under the explorer breaks out that mix.
- **Median granularity.** Because ACS rounds reported wages, weighted medians can sit on
  a common salary value and understate how different two groups really are at the middle;
  the top-of-field comparison is the more reliable read.
- **City title mapping is approximate.** Free-text civil-service titles are mapped to
  domains by keyword, so the all-occupations city view in particular is rough. Only
  cities that publish machine-readable, title-bearing payroll are included (NYC,
  Chicago, SF, Seattle, LA); many large cities (Houston, Dallas, Austin, Miami,
  Detroit) publish only PDFs or anonymized files and are absent.
- **Standard errors are robust, not design-based.** Replicate-weight standard errors
  are a documented future refinement; thin cells are flagged.
- **The thesis is descriptive co-movement, not a causal estimate.**

## References

- Congressional Budget Office (2024). *Comparing the Compensation of Federal and
  Private-Sector Employees, 2022.* https://www.cbo.gov/publication/60235
- U.S. Government Accountability Office (2012). *Federal Workers: Results of Studies on
  Federal Pay Varied Due to Differing Methodologies.* GAO-12-564.
  https://www.gao.gov/products/gao-12-564
- Andrew Biggs and Jason Richwine, American Enterprise Institute. https://www.aei.org/
- Sylvia Allegretto and Lawrence Mishel, Economic Policy Institute. https://www.epi.org/data/
- Robert Costrell and Michael Podgursky, on teacher-pension back-loading (TIAA
  Institute). https://www.tiaa.org/
- MissionSquare Research Institute (2024), on younger public employees' views of pay
  and benefits. https://www.missionsq.org/
- Pew Research Center and the Partnership for Public Service, on the age structure of
  the federal workforce. https://www.pewresearch.org/ , https://ourpublicservice.org/
- National Center for Education Statistics, Common Core of Data (teacher counts).
  https://nces.ed.gov/
- U.S. Census Bureau (ACS PUMS, ASPEP); U.S. Bureau of Labor Statistics (ECI, ECEC,
  CES); U.S. Bureau of Economic Analysis (national accounts). City payroll: NYC,
  Chicago, San Francisco, Seattle, and Los Angeles open-data portals.

On compression, unions, and the labor market behind the gap:

- George J. Borjas (2002). *The Wage Structure and the Sorting of Workers into the
  Public Sector.* NBER Working Paper 9313. https://www.nber.org/papers/w9313
- Maury Gittleman and Brooks Pierce (2012). *Compensation for State and Local Government
  Workers.* Journal of Economic Perspectives 26(1): 217-242.
  https://www.aeaweb.org/articles?id=10.1257/jep.26.1.217
- U.S. Bureau of Labor Statistics, *Union Members — 2025* (public 32.9% vs private
  5.9%). https://www.bls.gov/news.release/union2.nr0.htm
- David Card (2001). *The Effect of Unions on Wage Inequality in the U.S. Labor Market.*
  ILR Review 54(2): 296-315. https://davidcard.berkeley.edu/papers/union-wage-ineq.pdf
- Economic Policy Institute, *A Profile of Union Workers in State and Local Government*
  (2018). https://www.epi.org/publication/a-profile-of-union-workers-in-state-and-local-government-key-facts-about-the-sector-for-followers-of-janus-v-afscme-council-31/
- Michael Kremer (1993). *The O-Ring Theory of Economic Development.* Quarterly Journal
  of Economics 108(3): 551-575. https://academic.oup.com/qje/article-abstract/108/3/551/1881767
- Edward Lazear, Kathryn Shaw, and Christopher Stanton (2015). *The Value of Bosses.*
  Journal of Labor Economics 33(4): 823-861. https://www.nber.org/papers/w18317
- Ernesto Dal Bó, Frederico Finan, and Martín Rossi (2013). *Strengthening State
  Capabilities: The Role of Financial Incentives in the Call to Public Service.*
  Quarterly Journal of Economics 128(3): 1169-1218.
  https://academic.oup.com/qje/article-abstract/128/3/1169/1849634
- Caroline Hoxby and Andrew Leigh (2004). *Pulled Away or Pushed Out? Explaining the
  Decline of Teacher Aptitude in the United States.* American Economic Review 94(2):
  236-240. https://www.aeaweb.org/articles?id=10.1257/0002828041302073
- Thomas Lemieux, W. Bentley MacLeod, and Daniel Parent (2009). *Performance Pay and
  Wage Inequality.* Quarterly Journal of Economics 124(1): 1-49.
  https://academic.oup.com/qje/article/124/1/1/1890324
- Pew Charitable Trusts (2022), on the public-private wage-growth lag (BLS ECI).
  https://www.pew.org/en/research-and-analysis/articles/2022/02/07/government-wage-growth-lags-private-sector-by-largest-margin-on-record
- U.S. Government Accountability Office (2019). *Cybersecurity Workforce.* GAO-19-144.
  https://www.gao.gov/products/gao-19-144
- U.S. Bureau of Labor Statistics, *Occupational Employment and Wages in State and Local
  Government* (Spotlight on Statistics, 2021).
  https://www.bls.gov/spotlight/2021/occupational-employment-and-wages-in-state-and-local-government/

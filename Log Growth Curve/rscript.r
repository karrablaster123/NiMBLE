# Load necessary libraries
if (!require("readxl")) install.packages("readxl", repos = "http://cran.us.r-project.org")
if (!require("ggplot2")) install.packages("ggplot2", repos = "http://cran.us.r-project.org")
if (!require("dplyr")) install.packages("dplyr", repos = "http://cran.us.r-project.org")
if (!require("minpack.lm")) install.packages("minpack.lm", repos = "http://cran.us.r-project.org")
if (!require("lubridate")) install.packages("lubridate", repos = "http://cran.us.r-project.org")

library(lubridate)
library(readxl)
library(ggplot2)
library(dplyr)
library(minpack.lm)

# 1. Read data
df <- read_excel("/home/kb/MyStuff/Stuff/UToronto/NiMBLE Work/Projects/Log Growth Curve/data.xlsx")

# 2. Preprocess Dates (Convert to "Days from start")
df$Date <- parse_date_time(df$Date, orders = c("ymd", "mdy", "dmy"))
df$Time <- as.numeric(difftime(df$Date, min(df$Date), units = "days"))
# Create the log-transformed variable
df$log_y <- log(df$Number)

# 3. Define the Logistic Model
# R's nls uses the formula: y ~ model(x, parameters)
logistic_model <- function(t, L, k, x0) {
  # Calculate the exponent part
  exponent <- -k * (t - x0)
  exp_val <- exp(exponent)
  
  # Check if the calculation is breaking
  if (any(is.infinite(exp_val)) || any(is.nan(exp_val))) {
    cat(sprintf("[CRASH WARNING] Bad math detected!\n"))
  }
  # Return the actual calculation
  return(L / (1 + exp_val))
}

suggested_L  <- max(df$log_y, na.rm = TRUE)          # Peak of the logistic curve
suggested_x0 <- median(df$Time, na.rm = TRUE)        # Midpoint of the timeframe
suggested_k  <- 0.1                                  # A safe standard growth rate guess

# 4. Fit the model
# Start values correspond to your initial_guesses
fit <- nlsLM(log_y ~ logistic_model(Time, L, k, x0), 
             data = df, 
             start = list(L = suggested_L, k = suggested_k, x0 = suggested_x0))

# Extract parameters
params <- coef(fit)
L_fit <- params["L"]
k_fit <- params["k"]
x0_fit <- params["x0"]

cat(sprintf("R-squared: %.4f\n", summary(fit)$sigma^2)) # Note: nls summary handles residuals
# For exact R2 calculation to match your Python logic:
y_fit <- predict(fit)
ss_res <- sum((df$log_y - y_fit)^2)
ss_tot <- sum((df$log_y - mean(df$log_y))^2)
r2 <- 1 - (ss_res / ss_tot)
cat(sprintf("R-squared: %.4f\n", r2))
cat(sprintf("Fitted Parameters:\nCarrying Capacity (L): %.2f\nGrowth Rate (k): %.2f\nMidpoint (x0): %.2f\n", 
            L_fit, k_fit, x0_fit))

# 5. Generate smooth curve data
# Create a sequence of time points for the line
t_smooth <- seq(min(df$Time), max(df$Time), length.out = 100)
df_smooth <- data.frame(
  Time = t_smooth,
  y_smooth = logistic_model(t_smooth, L_fit, k_fit, x0_fit)
)

# 6. Plotting
ggplot(df, aes(x = Time, y = log_y)) +
  geom_point(color = "royalblue", size = 2, alpha = 0.6) +
  geom_line(data = df_smooth, aes(x = Time, y = y_smooth), 
            color = "red", linewidth = 1) +
  labs(title = "Bacterial Growth Curve Fit",
       x = "Time (Days)",
       y = "Log(Population)") +
  theme_minimal() +
  # Removed the unsupported alpha argument
  theme(panel.grid = element_line(linetype = "dashed", color = "gray80"))

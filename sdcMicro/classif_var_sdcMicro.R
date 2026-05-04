# Exploration initiale de sdcMicro, fonctionnalité permettant de classifier les
# variables

library(sdcMicro)
data(testdata)

# Step 1: AI-assisted variable classification
sdc <- AI_createSdcObj(dat = testdata, policy = "open")

# Step 2: AI-assisted anonymization
sdc <- AI_applyAnonymization(sdc, k = 3)

# Step 3: Extract the anonymized data
anon_data <- extractManipData(sdc)
head(anon_data)



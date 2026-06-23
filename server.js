console.log("Getting ready for launch, safety checks first : ");

const express = require('express');
console.log("express imported");

const cors = require('cors');
console.log("cors imported");

const apiRoutes = require('./routes/api.js');
console.log("routes imported");

const dotenv = require('dotenv');
console.log("dotenv imported");

dotenv.config();
const app = express();

//middlewares
app.use(cors());
app.use(express.json());

//API routes
app.use('/api', apiRoutes);

//host the server
console.log("4. Attempting to start server...");
app.listen(process.env.PORT || 3000, () => {
    console.log(`Server is running on http://localhost:${process.env.PORT || 3000}`);
})

const path = require("path");
const webpack = require("webpack");

const outDir = path.resolve(
    __dirname,
    "../package/appserver/static/ui"
);

module.exports = {
    entry: {
        editor: path.join(__dirname, "src/editor.jsx"),
        export: path.join(__dirname, "src/export.jsx"),
        import: path.join(__dirname, "src/import.jsx"),
        baselines: path.join(__dirname, "src/baselines.jsx"),
        assignment: path.join(__dirname, "src/assignment.jsx"),
        collection_review: path.join(__dirname, "src/collection_review.jsx"),
        collection_dashboard: path.join(__dirname, "src/collection_dashboard.jsx"),
        meta_collection_dashboard: path.join(
            __dirname,
            "src/meta_collection_dashboard.jsx"
        ),
        workspace_defaults: path.join(__dirname, "src/workspace_defaults.jsx"),
        review_requirements: path.join(__dirname, "src/review_requirements.jsx"),
        grants: path.join(__dirname, "src/grants.jsx"),
        labels: path.join(__dirname, "src/labels.jsx"),
        library: path.join(__dirname, "src/library.jsx"),
        transfer: path.join(__dirname, "src/transfer.jsx"),
    },
    output: {
        path: outDir,
        filename: "[name].js",
        clean: true,
    },
    resolve: {
        extensions: [".js", ".jsx"],
        alias: {
            react: path.resolve(__dirname, "node_modules/react"),
            "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
            "styled-components": path.resolve(
                __dirname,
                "node_modules/styled-components"
            ),
        },
    },
    module: {
        rules: [
            {
                test: /\.jsx?$/,
                exclude: /node_modules/,
                use: "babel-loader",
            },
        ],
    },
    plugins: [
        new webpack.DefinePlugin({
            "process.env.NODE_ENV": JSON.stringify(
                process.env.NODE_ENV || "production"
            ),
            "process.env.SC_ATTR": JSON.stringify("data-stigs-styled"),
        }),
    ],
    performance: { hints: false },
};

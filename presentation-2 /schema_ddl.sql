-- =====================================================================
-- DATABASE DEFINITION (DDL)
-- Project: Pharmacy Prescription and Medicine Stock Management System
-- Schema: 12 Normalized Relational Tables (3NF) + Trigger Guard
-- =====================================================================

CREATE DATABASE IF NOT EXISTS pharmacydb;
USE pharmacydb;

-- Drop child tables first to avoid foreign key dependency locks during reset
DROP TABLE IF EXISTS Stock_Movements;
DROP TABLE IF EXISTS Payments;
DROP TABLE IF EXISTS Sale_Items;
DROP TABLE IF EXISTS Sales;
DROP TABLE IF EXISTS Batches;
DROP TABLE IF EXISTS Medicines;
DROP TABLE IF EXISTS Purchases;
DROP TABLE IF EXISTS Prescriptions;
DROP TABLE IF EXISTS Customers;
DROP TABLE IF EXISTS Suppliers;
DROP TABLE IF EXISTS Manufacturers;
DROP TABLE IF EXISTS Categories;

-- 1. Categories Table
CREATE TABLE Categories (
    CategoryID INT AUTO_INCREMENT PRIMARY KEY,
    CategoryName VARCHAR(100) NOT NULL UNIQUE
);

-- 2. Manufacturers Table
CREATE TABLE Manufacturers (
    ManufacturerID INT AUTO_INCREMENT PRIMARY KEY,
    ManufacturerName VARCHAR(150) NOT NULL UNIQUE
);

-- 3. Suppliers Table
CREATE TABLE Suppliers (
    SupplierID INT AUTO_INCREMENT PRIMARY KEY,
    SupplierName VARCHAR(150) NOT NULL UNIQUE
);

-- 4. Customers Table
CREATE TABLE Customers (
    CustomerID INT AUTO_INCREMENT PRIMARY KEY,
    CustomerName VARCHAR(150) NOT NULL,
    Phone VARCHAR(20) NOT NULL UNIQUE
);

-- 5. Prescriptions Table
CREATE TABLE Prescriptions (
    PrescriptionID INT AUTO_INCREMENT PRIMARY KEY,
    CustomerID INT NOT NULL,
    DoctorName VARCHAR(150) NOT NULL,
    IssueDate DATE NOT NULL,
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE RESTRICT
);

-- 6. Purchases Table
CREATE TABLE Purchases (
    PurchaseID INT AUTO_INCREMENT PRIMARY KEY,
    SupplierID INT NOT NULL,
    PurchaseDate DATE NOT NULL,
    TotalAmount DECIMAL(10,2) NOT NULL CHECK (TotalAmount >= 0),
    OrderStatus VARCHAR(50) NOT NULL DEFAULT 'Delivered',
    FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID) ON DELETE RESTRICT
);

-- 7. Medicines Table
CREATE TABLE Medicines (
    MedicineID INT AUTO_INCREMENT PRIMARY KEY,
    CategoryID INT NOT NULL,
    ManufacturerID INT NOT NULL,
    MedicineName VARCHAR(150) NOT NULL,
    IsRestricted BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (CategoryID) REFERENCES Categories(CategoryID) ON DELETE RESTRICT,
    FOREIGN KEY (ManufacturerID) REFERENCES Manufacturers(ManufacturerID) ON DELETE RESTRICT
);

-- 8. Batches Table
CREATE TABLE Batches (
    BatchID INT AUTO_INCREMENT PRIMARY KEY,
    MedicineID INT NOT NULL,
    PurchaseID INT NOT NULL,
    BatchNumber VARCHAR(50) NOT NULL UNIQUE,
    ExpiryDate DATE NOT NULL,
    StockQuantity INT NOT NULL CHECK (StockQuantity >= 0),
    UnitCost DECIMAL(10,2) NOT NULL CHECK (UnitCost >= 0),
    FOREIGN KEY (MedicineID) REFERENCES Medicines(MedicineID) ON DELETE RESTRICT,
    FOREIGN KEY (PurchaseID) REFERENCES Purchases(PurchaseID) ON DELETE RESTRICT
);

-- 9. Sales Table
CREATE TABLE Sales (
    SaleID INT AUTO_INCREMENT PRIMARY KEY,
    CustomerID INT NOT NULL,
    PrescriptionID INT NULL,
    SaleDate DATE NOT NULL,
    GrandTotal DECIMAL(10,2) NOT NULL CHECK (GrandTotal >= 0),
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE RESTRICT,
    FOREIGN KEY (PrescriptionID) REFERENCES Prescriptions(PrescriptionID) ON DELETE RESTRICT
);

-- 10. Sale_Items Table
CREATE TABLE Sale_Items (
    SaleItemID INT AUTO_INCREMENT PRIMARY KEY,
    SaleID INT NOT NULL,
    BatchID INT NOT NULL,
    Quantity INT NOT NULL CHECK (Quantity > 0),
    UnitPrice DECIMAL(10,2) NOT NULL CHECK (UnitPrice >= 0),
    Discount DECIMAL(10,2) NOT NULL DEFAULT 0.00 CHECK (Discount >= 0),
    SubTotal DECIMAL(10,2) NOT NULL CHECK (SubTotal >= 0),
    FOREIGN KEY (SaleID) REFERENCES Sales(SaleID) ON DELETE RESTRICT,
    FOREIGN KEY (BatchID) REFERENCES Batches(BatchID) ON DELETE RESTRICT
);

-- 11. Payments Table
CREATE TABLE Payments (
    PaymentID INT AUTO_INCREMENT PRIMARY KEY,
    SaleID INT NOT NULL,
    PaymentMethod VARCHAR(50) NOT NULL,
    AmountPaid DECIMAL(10,2) NOT NULL CHECK (AmountPaid >= 0),
    FOREIGN KEY (SaleID) REFERENCES Sales(SaleID) ON DELETE RESTRICT
);

-- 12. Stock_Movements Table
CREATE TABLE Stock_Movements (
    MovementID INT AUTO_INCREMENT PRIMARY KEY,
    BatchID INT NOT NULL,
    MovementType VARCHAR(50) NOT NULL,
    Quantity INT NOT NULL,
    MovementDate DATE NOT NULL,
    FOREIGN KEY (BatchID) REFERENCES Batches(BatchID) ON DELETE RESTRICT
);

-- =====================================================================
-- DATABASE ENGINE TRIGGER
-- Enforces legal compliance for restricted Schedule H drugs
-- =====================================================================
DELIMITER //

DROP TRIGGER IF EXISTS EnforcePrescriptionRule //
CREATE TRIGGER EnforcePrescriptionRule
BEFORE INSERT ON Sale_Items
FOR EACH ROW
BEGIN
    DECLARE restricted_flag BOOLEAN;
    DECLARE linked_prescription INT;

    -- Look up restriction status of the medicine linked to this batch
    SELECT m.IsRestricted INTO restricted_flag
    FROM Batches b
    JOIN Medicines m ON b.MedicineID = m.MedicineID
    WHERE b.BatchID = NEW.BatchID;

    -- Look up if parent sales invoice has an associated doctor prescription
    SELECT PrescriptionID INTO linked_prescription
    FROM Sales
    WHERE SaleID = NEW.SaleID;

    -- Intercept transaction if restricted medication lacks an authorized prescription
    IF restricted_flag = TRUE AND linked_prescription IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'SALE BLOCKED: This medicine is restricted. A valid PrescriptionID is required.';
    END IF;
END;
//

DELIMITER ;
